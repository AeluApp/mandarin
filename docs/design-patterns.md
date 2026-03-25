# Aelu Design Pattern Library

Reusable visual patterns for the Aelu Mandarin learning platform. Every example uses real class names and token values from the codebase. When building new UI, compose from these patterns instead of inventing new ones.

Source files:
- `mandarin/web/static/style.css` -- all web CSS
- `mandarin/web/static/design-tokens.json` -- canonical token values
- `mandarin/web/static/visual-elevation.js` -- scroll reveal system
- `mandarin/web/static/scroll-engine.js` -- scroll progress engine
- `mandarin/web/static/webgl/ink-atmosphere.js` -- WebGL backgrounds
- `mandarin/web/static/webgl/celebrations.js` -- celebration effects
- `flutter_app/lib/theme/aelu_theme.dart` -- Flutter theme

---

## 1. Glass / Frosted Surface

Semi-transparent background with backdrop blur. Used for panels, stat cards, overlays, and any surface that floats above the page background. Wrapped in `@supports` for graceful fallback.

### Web

```html
<!-- Standard glass (78% opacity, 20px blur) -->
<div class="surface-glass">
  Content on frosted glass
</div>

<!-- Dense glass for overlays (88% opacity) -->
<div class="surface-glass-dense">
  Overlay content
</div>
```

The utility classes apply these properties:

```css
.surface-glass {
  backdrop-filter: var(--glass-blur);            /* blur(20px) saturate(1.2) */
  -webkit-backdrop-filter: var(--glass-blur);
  background: var(--glass-bg);                   /* surface @ 78% opacity */
  border: var(--glass-border);                   /* divider @ 40% opacity */
}

.surface-glass-dense {
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  background: var(--glass-bg-dense);             /* surface @ 88% opacity */
  border: var(--glass-border);
}
```

To build glass manually (e.g., custom blur radius):

```css
.my-element {
  backdrop-filter: blur(12px) saturate(1.1);
  -webkit-backdrop-filter: blur(12px) saturate(1.1);
  background: var(--glass-bg);
  border: var(--glass-border);
}
```

### Flutter

```dart
ClipRRect(
  borderRadius: BorderRadius.circular(12),
  child: BackdropFilter(
    filter: AeluTheme.glassBlur,        // blur(20, 20)
    child: Container(
      decoration: AeluTheme.glassDecoration(context),
      child: child,
    ),
  ),
)

// Dense glass for overlays:
AeluTheme.glassDecoration(context, dense: true)

// Lighter blur for compact elements:
AeluTheme.glassBlurLight  // blur(12, 12)
```

### Constraints

- Always include `-webkit-backdrop-filter` alongside `backdrop-filter`.
- Wrap in `@supports (backdrop-filter: blur(1px))` for web.
- Glass surfaces must have a visible background behind them to blur. They do not work against flat solid colors.
- Never exceed `blur(20px)` -- heavier blur is not part of the system.

---

## 2. Scroll Reveal

Elements fade and slide upward into view when they enter the viewport. Powered by `visual-elevation.js` using IntersectionObserver. Fires once per element (no re-hiding on scroll up).

### Web

```html
<!-- Single element reveal -->
<section data-reveal>
  <h2>This fades in when scrolled into view</h2>
  <p>20px upward drift, 0.6s duration, ease-upward curve.</p>
</section>
```

The CSS handles the animation:

```css
[data-reveal] {
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.6s var(--ease-upward), transform 0.6s var(--ease-upward);
}

[data-reveal].is-revealed {
  opacity: 1;
  transform: translateY(0);
}
```

JS adds `.is-revealed` when the element is 10% visible (with 30px bottom margin).

### Progressive enhancement -- native scroll-driven animation

```html
<!-- Uses CSS scroll-timeline where supported, falls back to JS -->
<div class="scroll-reveal">Content</div>
```

```css
@supports (animation-timeline: view()) {
  .scroll-reveal {
    animation: scrollRevealUp linear both;
    animation-timeline: view();
    animation-range: entry 0% entry 100%;
  }
}
```

### Constraints

- Reveals fire once. Do not use for content that should re-animate.
- The observer threshold is `0.1` with `rootMargin: '0px 0px -30px 0px'`. Do not change these without considering mobile viewport sizes.
- Respects `prefers-reduced-motion: reduce` -- all transforms and opacity are immediately set to final values.

---

## 3. Card Component (Panel)

The primary content container. Transparent background with a top divider (horizon line). No box, no card borders, no border-radius in the base version. Glass blur is layered on via `@supports`.

### Web

```html
<div class="panel">
  <h3>Session Summary</h3>
  <div class="panel-row">
    <span class="label">Cards reviewed</span>
    <span class="value">24</span>
  </div>
  <div class="panel-row">
    <span class="label">Accuracy</span>
    <span class="value value-good">88%</span>
  </div>
</div>
```

```css
.panel {
  background: transparent;
  border: none;
  border-top: 1px solid var(--color-divider);
  border-radius: 0;
  padding: var(--space-3) var(--space-4);       /* 0.75rem 1rem */
  margin: var(--space-2) 0;
}
```

With glass (applied automatically via `@supports`):

```css
@supports (backdrop-filter: blur(1px)) {
  .panel {
    backdrop-filter: blur(20px) saturate(1.2);
    -webkit-backdrop-filter: blur(20px) saturate(1.2);
    background: color-mix(in srgb, var(--color-surface) 82%, transparent);
    border: var(--glass-border);
  }
}
```

### Collapsible panel

```html
<div class="panel collapsible">
  <h3>
    <button class="panel-toggle" aria-expanded="true">
      Details
      <span class="panel-toggle-icon" aria-hidden="true">&#x25BE;</span>
    </button>
  </h3>
  <div class="panel-body">
    <!-- content -->
  </div>
</div>
```

### Constraints

- Panels use `border-radius: 0` in the base system. The `border-radius: var(--radius-card)` (8px) is only applied via the `.panel, .panel-body, .metric-card` rule for specific card contexts.
- Never add `box-shadow` to `.panel` directly. Shadow comes from the glass system.
- Use `.value-good` for positive metrics (sage color) and `.value-warn` for caution (olive color). Never use red.

---

## 4. Button Styles

Two tiers: primary (filled accent) and secondary (outlined). Both have spring-bounce press feedback and lift-on-hover.

### Web -- Primary

```html
<button class="btn-primary">Begin session</button>
```

Key properties:
```css
.btn-primary {
  background: var(--color-accent);               /* #946070 bougainvillea rose */
  color: var(--color-on-accent);                 /* #FFFFFF */
  border: none;
  padding: 14px 32px;                            /* var(--btn-padding) */
  border-radius: var(--radius-lg);               /* 6px */
  font-family: var(--font-body);
  font-size: var(--text-base);
  font-weight: 600;
  min-height: 44px;
  min-width: 44px;
}
/* Hover: lift 2px + accent shadow glow */
/* Active: scale(0.95) + focus ring */
/* Release: spring bounce back via --ease-spring */
```

### Web -- Secondary

```html
<button class="btn-secondary">View details</button>
```

```css
.btn-secondary {
  background: transparent;
  color: var(--color-accent);
  border: 1px solid var(--color-accent-dim);     /* #7A5060 */
  padding: 14px 24px;
  border-radius: var(--radius-lg);               /* 6px */
}
/* Hover: lift 2px + 6% accent tinted background */
```

### Size modifiers

```html
<!-- Small -->
<button class="btn-primary btn-sm">Save</button>

<!-- Large CTA (custom padding, used for #btn-start) -->
<button class="btn-primary" style="padding: 18px 48px; font-size: var(--text-lg);">
  Begin
</button>
```

```css
.btn-sm {
  font-size: var(--text-xs);                     /* 0.694rem */
  padding: var(--space-2) var(--space-3);         /* 0.5rem 0.75rem */
  min-height: 44px;
}
```

### Web -- Danger

```html
<button class="btn-danger btn-sm">Delete account</button>
```

```css
.btn-danger {
  background: var(--color-incorrect);            /* warm brown, NOT red */
  color: var(--color-on-accent);
  border: none;
  border-radius: var(--radius-sm);               /* 2px */
}
```

### Constraints

- Minimum touch target: 44px height and width (Apple HIG). On mobile, bumped to 48px.
- Spring easing (`--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1)`) is only for the release/bounce-back after press. Do not use spring for hover.
- The danger button uses `--color-incorrect` (warm brown #806058), never literal red.
- Disabled state: `opacity: 0.4; cursor: not-allowed; pointer-events: none`.

---

## 5. Typography Hierarchy

Serif throughout. Four stacks: headings (Cormorant Garamond), body (Source Serif 4), hanzi (Noto Serif SC), mono (SF Mono).

### Type scale

| Token | Size | Use |
|-------|------|-----|
| `--text-display` | `clamp(2.2rem, 5vw, 3.2rem)` | Hero moments, logo mark |
| `--text-3xl` | `clamp(1.6rem, 3.5vw, 2.074rem)` | Page titles |
| `--text-2xl` | `clamp(1.4rem, 2.8vw, 1.728rem)` | Section headings |
| `--text-xl` | `clamp(1.2rem, 2vw, 1.44rem)` | Sub-headings |
| `--text-lg` | `1.2rem` | Panel headings, emphasis |
| `--text-base` | `1rem` | Body text |
| `--text-sm` | `0.833rem` | Secondary text, labels |
| `--text-xs` | `0.694rem` | Captions, timestamps |

### Web

```html
<!-- Display (hero) -->
<h1 class="text-display-hero">Patient Mandarin study</h1>

<!-- Display hanzi -->
<span class="text-display-hanzi">漫</span>

<!-- Heading with animated underline reveal -->
<h2 class="heading-reveal">Your Progress</h2>

<!-- Panel heading -->
<h3 style="font-family: var(--font-heading); font-size: var(--text-sm);
           color: var(--color-text-dim); font-weight: 600;
           letter-spacing: var(--tracking-normal);">
  Session Summary
</h3>

<!-- Body text (default) -->
<p>Review accuracy this week.</p>

<!-- Caption / faint -->
<span style="font-size: var(--text-xs); color: var(--color-text-faint);">
  Last studied 2 hours ago
</span>
```

Hero display classes:

```css
.text-display-hero {
  font-family: var(--font-heading);
  font-size: clamp(2.8rem, 6vw, 4.5rem);
  line-height: var(--lh-display);                /* 1.1 */
  letter-spacing: var(--tracking-tight);          /* 0.01em */
  font-weight: 300;
}

.text-display-hanzi {
  font-family: var(--font-hanzi);
  font-size: clamp(3rem, 8vw, 6rem);
  line-height: 1;
  color: var(--color-accent);
}
```

### Constraints

- All headings use `var(--font-heading)` (Cormorant Garamond). Never use sans-serif.
- Body text uses `var(--font-body)` (Source Serif 4). All sizes use 1.2 ratio (minor third) scale.
- Hanzi text must use `var(--font-hanzi)` (Noto Serif SC) to avoid CJK rendering issues.
- Letter spacing: `--tracking-tight` (0.01em) for large display text, `--tracking-normal` (0.03em) for headings, `--tracking-wide` (0.15em) for labels/logo text.
- Line heights are paired to sizes: display=1.1, 3xl=1.2, xl/lg=1.3, base=1.6, sm=1.5, xs=1.4.

---

## 6. Skeleton Loading

Shimmer animation for placeholder content while data loads. Uses a moving gradient.

### Web

```html
<div class="panel-skeleton">
  <div class="skeleton-line"></div>
  <div class="skeleton-line short"></div>
  <div class="skeleton-line"></div>
</div>
```

```css
.skeleton-line {
  height: var(--skeleton-height);                /* 14px */
  background: var(--color-surface-alt);
  opacity: 0.4;
  border-radius: 0;
  margin: var(--space-2) 0;
}

.skeleton-line.short {
  width: 60%;
}

/* Shimmer animation (applied via .skeleton-line in the keyframes section) */
@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton-line {
  background: linear-gradient(90deg,
    var(--color-surface-alt) 25%,
    color-mix(in srgb, var(--color-surface-alt) 60%, var(--color-base)) 50%,
    var(--color-surface-alt) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}
```

### Constraints

- Skeleton lines have `border-radius: 0` (matching the zero-radius brand).
- The shimmer duration is 1.5s with `ease-in-out`. Do not speed it up -- the pace conveys calm.
- The `.short` modifier is 60% width. Use it for the last line in a group to suggest content variety.

---

## 7. Empty State

Centered message with an optional illustration (or auto-generated SVG vignette). The default `::before` pseudo-element draws a horizon + sun motif.

### Web -- Without illustration

```html
<div class="empty-state">
  No sessions yet. Begin when you are ready.
</div>
```

This automatically renders the horizon+sun SVG vignette via `::before`, colored by `--color-illustration` (which maps to `--color-accent`).

### Web -- With illustration

```html
<div class="empty-state">
  <img class="empty-state-illustration"
       src="/static/illustrations/morning-courtyard.png"
       alt="" loading="lazy">
  <p>No sessions yet. Begin when you are ready.</p>
</div>
```

When `.empty-state-illustration` is present, the `::before` vignette is automatically hidden via `:has()` (with `.has-illustration` fallback for older browsers).

The illustration floats gently:

```css
.empty-state-illustration {
  animation: gentleBloom 0.6s var(--ease-upward) 0.1s forwards,
             illustrationFloat 6s ease-in-out 1s infinite;
  box-shadow: var(--shadow-md);
  max-width: 340px;
  border-radius: 8px;
}
```

### Web -- Timeline empty state

```html
<div class="empty-state">
  <div class="empty-state-timeline"></div>
  <p>Your study timeline will appear here.</p>
</div>
```

The timeline draws a horizontal ink line with a dot at the end.

### Constraints

- Empty state text is italic, `var(--text-sm)`, `var(--color-text-faint)`.
- Voice: factual, forward-looking. Never guilt ("You haven't studied!"). Never praise. Say "No sessions yet" not "Get started today!"
- Illustrations use `pointer-events: none` and are decorative (`alt=""`).
- In dark mode, illustrations get a heavier shadow (`--shadow-lg`).

---

## 8. Horizon Divider

The signature visual motif. A thin centered line that represents the horizon. Used between sections, in headers, and as the panel border-top.

### Web

```html
<!-- Standalone horizon line -->
<div class="horizon"></div>

<!-- In header (with draw animation) -->
<header>
  <span class="logo-mark">漫</span>
  <div class="horizon"></div>
</header>
```

```css
.horizon {
  width: var(--horizon-width);                   /* 48px */
  height: 1px;
  background: var(--color-divider);              /* #D8D0C4 light / #3A3530 dark */
  margin: var(--space-2) auto;
}

/* In header: animated draw-in */
header .horizon {
  animation: horizonDraw 0.8s var(--ease-upward) 0.3s;
  animation-fill-mode: backwards;
}

@keyframes horizonDraw {
  from { width: 0; opacity: 0; }
  to   { width: var(--horizon-width); opacity: 1; }
}
```

Panel border-tops serve the same purpose:

```css
.panel {
  border-top: 1px solid var(--color-divider);
}
```

### Constraints

- Horizon width is always `48px` (the `--horizon-width` token). Do not make it wider.
- Horizon color is `--color-divider`, never accent or text color.
- 1px height only. Never use thicker dividers.
- Use `margin: var(--space-2) auto` for centered placement.

---

## 9. WebGL Atmosphere

Full-screen animated gradient mesh background using Three.js. Four scene presets with different color temperatures and particle densities.

### Web

```html
<!-- Include Three.js first, then the atmosphere script -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r169/three.min.js" async></script>
<script src="/static/webgl/ink-atmosphere.js" defer></script>

<!-- Place the container in your page -->
<div id="webgl-atmosphere" data-scene="marketing"></div>
```

Available `data-scene` values:

| Scene | Purpose | Character |
|-------|---------|-----------|
| `marketing` | Landing/hero page | Highest fidelity, ink particles |
| `login` | Auth pages | Gradient mesh + grain |
| `dashboard` | Main app | Ambient, lightest |
| `admin` | Admin panel | Cool-toned mesh |

### Integration with Scroll Engine

The atmosphere responds to scroll progress automatically:

```javascript
// scroll-engine.js pushes progress to AeluScene:
if (window.AeluScene && window.AeluScene.setScrollProgress) {
  AeluScene.setScrollProgress(totalScrollProgress);  // 0-1
}
```

### Constraints

- Falls back to CSS gradient mesh if WebGL is unavailable or `prefers-reduced-motion` is active.
- Pauses the render loop when the tab is hidden or the canvas is off-screen (battery-conscious).
- The `#webgl-atmosphere` div must exist in the DOM before the script loads.
- Only one scene instance per page.

---

## 10. Celebrations

Canvas-based (2D, not WebGL) overlay effects. Lightweight, auto-cleanup, respect reduced motion.

### API

```javascript
// Paper lanterns -- rising glowing orbs for session complete
AeluCelebrations.paperLanterns();
AeluCelebrations.paperLanterns({ count: 10 });

// Ink bloom -- radial wash expanding from an element (correct answer)
AeluCelebrations.inkBloom(document.querySelector('.msg-correct'));
AeluCelebrations.inkBloom(element, { color: '#5A7A5A', duration: 600 });

// Ink settle -- character settles with underline (correct answer)
AeluCelebrations.inkSettle(element);

// Ink scatter -- particles disperse (incorrect answer, gentle)
AeluCelebrations.inkScatter(element);
```

### Details

| Function | Trigger | Duration | Color source |
|----------|---------|----------|-------------|
| `paperLanterns` | Session complete | 2.5s | Mastery palette (durable, stable, stabilizing, accent) |
| `inkBloom` | Correct answer | 600ms | `--color-correct` (sage green) |
| `inkSettle` | Correct answer | CSS class | Adds `.ink-settle` class + boosts WebGL |
| `inkScatter` | Incorrect answer | 500ms | `--color-incorrect` (warm brown) |

### Constraints

- All functions are no-ops when `prefers-reduced-motion: reduce` is active.
- Paper lanterns are NOT confetti. They are calm, glowing, rising orbs. The count defaults to 7.
- Ink scatter uses warm brown, never red. The brand does not use alarm colors.
- Canvas overlays auto-remove from DOM after their duration completes.
- `inkSettle` and `inkScatter` also nudge the WebGL atmosphere intensity via `AeluScene.boostIntensity()`.

---

## 11. Dark Mode

Theme is set by time of day (JS on page load) or OS preference. CSS custom properties swap all colors. Three mechanisms, in cascade order:

### How it works

1. **OS preference** -- `@media (prefers-color-scheme: dark)` sets dark tokens on `:root`.
2. **Time-of-day override** -- JS sets `data-theme="dark"` or `data-theme="light"` on `<html>` based on local hour (dark after 7pm, before 7am). This overrides the media query.
3. **High contrast layer** -- `data-contrast="high"` layers on top of either theme.

### Adding theme-aware styles

Always use CSS custom properties. Never hardcode colors.

```css
/* CORRECT -- automatically adapts */
.my-element {
  color: var(--color-text);
  background: var(--color-surface-alt);
  border-bottom: 1px solid var(--color-divider);
}

/* WRONG -- breaks in dark mode */
.my-element {
  color: #2A3650;
  background: #EAE2D6;
}
```

For theme-specific overrides when tokens are not sufficient:

```css
/* Dark-specific adjustment */
html[data-theme="dark"] .my-element {
  box-shadow: var(--shadow-lg);     /* heavier shadow needed in dark */
}
```

### Key color token pairs

| Token | Light | Dark |
|-------|-------|------|
| `--color-base` | `#F2EBE0` (warm linen) | `#1C2028` (deep indigo) |
| `--color-text` | `#2A3650` (coastal indigo) | `#E4DDD0` (warm cream) |
| `--color-accent` | `#946070` (bougainvillea) | `#B07888` (lighter rose) |
| `--color-divider` | `#D8D0C4` | `#3A3530` |
| `--color-shadow` | `rgba(42,54,80,0.04)` | `rgba(0,0,0,0.12)` |

### Flutter

```dart
// AeluTheme resolves brightness automatically:
final shadows = AeluTheme.shadowOf(context, AeluTheme.shadowMd);
final decoration = AeluTheme.glassDecoration(context);
// Both check Theme.of(context).brightness internally.
```

### Constraints

- Every new color must have both light and dark variants defined.
- Dark mode shadows are 3-5x heavier than light mode (compare `rgba(42,54,80,0.04)` vs `rgba(0,0,0,0.12)`).
- Dark mode glass uses `--color-surface-alt` (not `--color-surface`) as the base, at 72% opacity instead of 78%.
- Never use `@media (prefers-color-scheme: dark)` for component styles. Use `html[data-theme="dark"]` so the time-of-day override works.

---

## 12. Motion Tokens

Seven duration tiers and four easing curves. Every animation in the system uses these tokens.

### Durations

| Token | Value | Use |
|-------|-------|-----|
| `--duration-press` | `0.08s` | Button press feedback (near-instant) |
| `--duration-snappy` | `0.12s` | Feedback bar confirmation |
| `--duration-fast` | `0.18s` | Hover transitions, quick state changes |
| `--duration-base` | `0.3s` | Standard transitions (panels, reveals) |
| `--duration-slow` | `0.4s` | Larger element transitions |
| `--duration-ambient` | `0.8s` | Shimmer loops, ambient pulses |
| `--duration-float` | `1.5s` | Illustration hover float |

### Easing curves

| Token | Value | Use |
|-------|-------|-----|
| `--ease-default` | `cubic-bezier(0.25, 0.1, 0.25, 1)` | General transitions |
| `--ease-upward` | `cubic-bezier(0.16, 1, 0.3, 1)` | Elements arriving (scroll reveals, page entry). Decelerates into rest. |
| `--ease-exit` | `cubic-bezier(0.4, 0, 1, 1)` | Elements leaving (ease-in, accelerates out) |
| `--ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Button bounce-back after press. Physical gesture feel. |

### Usage pattern

```css
/* Element arriving: slow deceleration */
.element-enter {
  transition: opacity var(--duration-base) var(--ease-upward),
              transform var(--duration-base) var(--ease-upward);
}

/* Hover feedback: quick and default */
.element:hover {
  transition: transform var(--duration-fast) var(--ease-default);
}

/* Button release bounce-back */
.button:not(:active) {
  transition: transform 0.4s var(--ease-spring);
}
```

### Flutter equivalents

```dart
AeluTheme.durationPress    // 100ms
AeluTheme.durationSnappy   // 150ms
AeluTheme.durationFast     // 200ms
AeluTheme.durationNormal   // 300ms
AeluTheme.springCurve      // Cubic(0.34, 1.56, 0.64, 1)
AeluTheme.pressScale        // 0.98 (button press scale factor)
```

### Constraints

- Motion decelerates into rest. Things arrive, they do not pop or bounce (except button release).
- `--ease-spring` is reserved for button press bounce-back only. Never use it for page transitions or reveals.
- `--ease-upward` is the default for anything entering the viewport.
- All animations must be wrapped in `@media (prefers-reduced-motion: reduce)` guards that disable them.
- Maximum reveal animation duration is 0.6s. Anything longer feels sluggish.

---

## 13. Shadow / Depth System

Six levels from `xs` (barely visible) to `2xl` (dramatic modal depth). Light and dark modes have separate shadow values.

### Web

| Level | Token | Light value | Use |
|-------|-------|-------------|-----|
| 0 | `--shadow-xs` | `0 1px 1px rgba(42,54,80,0.04)` | Subtle surface distinction |
| 1 | `--shadow-sm` | `0 1px 3px ..., 0 1px 2px ...` | Cards at rest |
| 2 | `--shadow-md` | `0 2px 6px ..., 0 1px 3px ...` | Illustrations, images |
| 3 | `--shadow-lg` | `0 8px 24px rgba(0,0,0,0.08), ...` | Hover state, elevated cards |
| 4 | `--shadow-xl` | `0 16px 48px rgba(0,0,0,0.10), ...` | Modals, important overlays |
| 5 | `--shadow-2xl` | `0 24px 64px rgba(0,0,0,0.14), ...` | Hero elements |

```css
/* Card at rest */
.card { box-shadow: var(--shadow-sm); }

/* Card on hover -- lift to lg */
.card:hover { box-shadow: var(--shadow-lg); }
```

### Flutter

```dart
// Named indices for clarity
AeluTheme.shadowXs   // 0
AeluTheme.shadowSm   // 1
AeluTheme.shadowMd   // 2
AeluTheme.shadowLg   // 3
AeluTheme.shadowXl   // 4
AeluTheme.shadow2xl   // 5

// Usage -- auto-resolves light/dark:
Container(
  decoration: BoxDecoration(
    boxShadow: AeluTheme.shadowOf(context, AeluTheme.shadowMd),
  ),
)
```

### Constraints

- Dark mode shadows are 3-5x stronger than light mode. The tokens handle this automatically.
- Hover transitions should go up exactly one level (e.g., `sm` to `lg`, not `sm` to `2xl`).
- Shadow color in light mode is tinted slate-blue (`rgba(42,54,80,...)`), not pure black.
- Never use `box-shadow` for colored glows except on button hover (where accent-tinted glow is intentional).

---

## 14. Admin Glass Cards (Metric Card)

Glass-backed metric cards for the admin dashboard. Grid layout, center-aligned values, hover lift.

### Web

```html
<div class="metrics-grid">
  <div class="metric-card" title="Total active users in the last 30 days">
    <div class="metric-value">1,247</div>
    <div class="metric-label">Active Users</div>
  </div>
  <div class="metric-card kpi-good">
    <div class="metric-value">94.2%</div>
    <div class="metric-label">Uptime</div>
  </div>
  <div class="metric-card kpi-warn">
    <div class="metric-value">3.2s</div>
    <div class="metric-label">Avg Response</div>
  </div>
</div>
```

```css
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--space-3);
}

.metric-card {
  padding: var(--space-4);
  border-radius: 8px;
  text-align: center;
  backdrop-filter: blur(16px) saturate(1.15);
  -webkit-backdrop-filter: blur(16px) saturate(1.15);
  background: var(--glass-bg);
  border: var(--glass-border);
  transition: transform 0.2s var(--ease-default),
              box-shadow 0.2s var(--ease-default);
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.metric-value {
  font-family: var(--font-heading);
  font-size: var(--text-2xl);
  color: var(--color-accent);
}

.metric-label {
  font-family: var(--font-body);
  font-size: var(--text-sm);
  color: var(--color-text-dim);
  margin-top: var(--space-1);
}
```

### KPI status coloring

```css
.kpi-good .metric-value { color: var(--color-correct); }
.kpi-warn .metric-value { color: var(--color-mastery-stabilizing); }
.kpi-bad  .metric-value { color: var(--color-incorrect); }
```

### Constraints

- Metric cards always use glass. They need a visible background behind them.
- The grid uses `auto-fit` with `minmax(150px, 1fr)` -- cards auto-wrap responsively.
- `metric-value` uses heading font (Cormorant Garamond) at `--text-2xl`. Never use body font for values.
- Hover lift is `-2px translateY` with `--shadow-lg`. Do not increase.

---

## 15. Staggered Entrance

Two systems for staggered entry animation: CSS class-based (for dynamic JS-driven lists) and attribute-based (for static scroll-revealed content).

### System A: `stagger-children` (scroll-triggered, attribute-based)

Used with the scroll reveal system. Parent gets the class, children stagger automatically when scrolled into view.

```html
<div class="stagger-children" data-reveal>
  <div>First item (0ms delay)</div>
  <div>Second item (60ms delay)</div>
  <div>Third item (120ms delay)</div>
  <div>Fourth item (180ms delay)</div>
</div>
```

```css
.stagger-children > * {
  opacity: 0;
  transform: translateY(12px);
  transition: opacity 0.4s var(--ease-upward), transform 0.4s var(--ease-upward);
}

.stagger-children.is-revealed > *:nth-child(1) { transition-delay: 0ms; }
.stagger-children.is-revealed > *:nth-child(2) { transition-delay: 60ms; }
.stagger-children.is-revealed > *:nth-child(3) { transition-delay: 120ms; }
.stagger-children.is-revealed > *:nth-child(4) { transition-delay: 180ms; }
.stagger-children.is-revealed > *:nth-child(5) { transition-delay: 240ms; }
.stagger-children.is-revealed > *:nth-child(6) { transition-delay: 300ms; }
.stagger-children.is-revealed > *:nth-child(n+7) { transition-delay: 360ms; }
```

### System B: `panel-stagger-enter` (CSS animation, for panels)

Used for panels that animate on page load or section switch. Each panel gets the class individually.

```html
<div class="panel panel-stagger-enter">Panel 1</div>
<div class="panel panel-stagger-enter">Panel 2</div>
<div class="panel panel-stagger-enter">Panel 3</div>
```

```css
.panel.panel-stagger-enter {
  animation: panelEnter var(--duration-base) var(--ease-upward) backwards;
}

.panel.panel-stagger-enter:nth-child(1) { animation-delay: 0s; }
.panel.panel-stagger-enter:nth-child(2) { animation-delay: 0.05s; }
.panel.panel-stagger-enter:nth-child(3) { animation-delay: 0.1s; }
/* ... through :nth-child(8) at 0.35s */

@keyframes panelEnter {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

### System C: `data-reveal-child` (JS-driven, 80ms stagger)

For mixed content within a scroll-revealed section. The JS sets `transition-delay` dynamically.

```html
<section data-reveal class="stagger-children">
  <div data-reveal-child>Item A</div>
  <div data-reveal-child>Item B</div>
  <div data-reveal-child>Item C</div>
</section>
```

`visual-elevation.js` sets `child.style.transitionDelay = (i * 80) + 'ms'` and adds `.is-revealed` to each child.

### Constraints

- Stagger delay is 60ms per child (CSS system) or 80ms per child (JS system). Do not exceed 100ms per item or the cascade feels sluggish.
- Maximum stagger chain: items 7+ all share the same delay (360ms) to prevent long waits.
- Panel stagger uses 50ms intervals (tighter than general stagger) because panels are larger visual elements.
- All stagger animations are disabled under `prefers-reduced-motion: reduce`.
- The drift direction is always upward (positive Y to 0). Never slide from left/right or downward.

---

## Scroll Engine API Reference

For scroll-progress-driven animations (parallax, continuous opacity, WebGL sync).

```javascript
// Listen to a named section's progress (0-1)
AeluScroll.onProgress('hero', function(progress) {
  // progress: 0 when section enters viewport bottom, 1 when it leaves top
});

// Listen to total page scroll progress
AeluScroll.onGlobalProgress(function(progress) {
  // progress: 0 at top, 1 at bottom
});

// Get current progress (synchronous)
var p = AeluScroll.getProgress('hero');
var total = AeluScroll.getTotalProgress();

// Interpolate a value based on scroll
var opacity = AeluScroll.scrollDriven('hero', 1, 0);  // 1 at start, 0 at end

// Smooth scroll to a section
AeluScroll.scrollTo('features', { offset: -50 });

// Force re-measurement after dynamic content changes
AeluScroll.refresh();
```

### HTML setup

```html
<section data-scroll-section="hero">
  <!-- Use --scroll-progress in CSS -->
  <div style="opacity: calc(1 - var(--scroll-progress))">
    Fades out as you scroll
  </div>
</section>

<!-- Pinned section (position: sticky + scroll animation) -->
<section data-scroll-section="features" data-scroll-pin>
  ...
</section>
```

### Constraints

- Scroll engine runs on `requestAnimationFrame` with passive scroll listener. Never block the main thread in callbacks.
- `--scroll-progress` is set as an inline CSS custom property with 4 decimal places.
- Scroll engine automatically pushes total progress to `AeluScene.setScrollProgress()` if the WebGL atmosphere is initialized.
- Re-registers sections on DOM mutations (100ms debounce). Call `AeluScroll.refresh()` manually after large layout changes.
