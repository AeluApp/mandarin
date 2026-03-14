# Aelu UI Icon Reference

SVG sprite sheet: `ui-icons.svg`

All icons use `viewBox="0 0 24 24"`, `stroke="currentColor"`, `stroke-width="1.5"`, `fill="none"`, `stroke-linecap="round"`, `stroke-linejoin="round"`. Line-art style matching the Civic Sanctuary aesthetic (no filled/solid icons, no rounded corners).

## Usage

Reference any icon via the `<use>` element:

```html
<svg width="24" height="24" aria-hidden="true">
  <use href="/path/to/ui-icons.svg#icon-play"/>
</svg>
```

Or inline the sprite sheet in `<body>` and reference with fragment-only href:

```html
<svg width="24" height="24" aria-hidden="true">
  <use href="#icon-play"/>
</svg>
```

Icons inherit `currentColor` from their parent element, so color is controlled via CSS `color` on the container.

---

## Navigation

| Icon | Symbol ID | Description | Usage Context |
|------|-----------|-------------|---------------|
| Home | `icon-home` | House with door detail | Dashboard link, main navigation return |
| Back | `icon-back` | Left-pointing chevron | In-page back navigation (compact) |
| Settings | `icon-settings` | Gear / cog | Preferences, configuration access |
| Menu | `icon-menu` | Three horizontal lines | Mobile hamburger menu, navigation drawer |

## Actions

| Icon | Symbol ID | Description | Usage Context |
|------|-----------|-------------|---------------|
| Play | `icon-play` | Right-pointing triangle | Start playback, begin session |
| Pause | `icon-pause` | Two vertical bars | Pause playback or session |
| Stop | `icon-stop` | Square | Stop / end session |
| Refresh | `icon-refresh` | Rotating arrows | Retry, reload content |
| Close | `icon-close` | X (diagonal cross) | Close overlay, dismiss modal |
| Check | `icon-check` | Checkmark | Correct answer, task complete, confirmation |
| X-mark | `icon-x-mark` | X inside a square frame | Incorrect answer, error state (distinct from close) |

## Learning

| Icon | Symbol ID | Description | Usage Context |
|------|-----------|-------------|---------------|
| Book | `icon-book` | Open book | Graded reader, reading section |
| Headphones | `icon-headphones` | Over-ear headphones | Listening practice section |
| Microphone | `icon-microphone` | Mic with stand | Speaking drill, tone recording |
| Pencil | `icon-pencil` | Angled pencil | Writing practice, editing context notes |
| Eye | `icon-eye` | Eye with iris | Review mode, visibility toggle (show/hide pinyin) |
| Lightbulb | `icon-lightbulb` | Bulb with base | Hints, insights, context notes display |

## Status

| Icon | Symbol ID | Description | Usage Context |
|------|-----------|-------------|---------------|
| Star | `icon-star` | Five-pointed star | Mastery indicator, favorites |
| Streak fire | `icon-streak-fire` | Flame with inner flame | Consecutive day streak counter |
| Clock | `icon-clock` | Circle with clock hands | Session duration, time remaining |
| Calendar | `icon-calendar` | Calendar with date line | Schedule, session history dates |
| Chart up | `icon-chart-up` | Upward trending line with arrow | Positive accuracy trend, improvement |
| Chart down | `icon-chart-down` | Downward trending line with arrow | Negative trend, areas needing attention |

## Media

| Icon | Symbol ID | Description | Usage Context |
|------|-----------|-------------|---------------|
| Volume on | `icon-volume-on` | Speaker with sound waves | Audio enabled, sound toggle on-state |
| Volume off | `icon-volume-off` | Speaker with X | Audio muted, sound toggle off-state |
| Speed | `icon-speed` | Speedometer / gauge | Playback rate control (0.7x, 1.0x, 1.2x) |
| Skip forward | `icon-skip-forward` | Triangle + bar pointing right | Next passage, advance in media |
| Skip back | `icon-skip-back` | Triangle + bar pointing left | Previous passage, rewind in media |

## Utility

| Icon | Symbol ID | Description | Usage Context |
|------|-----------|-------------|---------------|
| Download | `icon-download` | Downward arrow into tray | Save file, export CSV |
| Share | `icon-share` | Three connected nodes | Share referral link, share content |
| Copy | `icon-copy` | Overlapping rectangles | Copy referral link to clipboard |
| External link | `icon-external-link` | Box with arrow exiting | Open in new tab, external resource link |
| Search | `icon-search` | Magnifying glass | Search vocabulary, filter content |
| Filter | `icon-filter` | Funnel | HSK level filter, content type filter |

## App-Specific

| Icon | Symbol ID | Description | Usage Context |
|------|-----------|-------------|---------------|
| Arrow right | `icon-arrow-right` | Horizontal arrow pointing right | Submit answer button (replaces `&rarr;`) |
| Arrow left | `icon-arrow-left` | Horizontal arrow pointing left | Back to dashboard button (replaces `&larr;`) |
| Plus | `icon-plus` | Plus sign | Expand collapsible panel (replaces `+` text) |
| Minus | `icon-minus` | Horizontal line | Collapse panel (replaces `−` text) |
| Sound toggle | `icon-sound-toggle` | Speaker with single wave | Sound on/off toggle in status bar |
| Sparkline | `icon-sparkline` | Rising/falling polyline | Inline trend visualization |
| Horizon | `icon-horizon` | Horizontal line with upward notch | Decorative section divider |
| Feedback | `icon-feedback` | Speech bubble | Feedback bar, NPS survey trigger |
| Export | `icon-export` | Document with upward arrow | CSV export links in export panel |
| Invite | `icon-invite` | Person silhouette with plus | Referral / invite-a-friend panel |
| Progress | `icon-progress` | Horizontal bar with partial fill | Session progress indicator |

---

## Inline SVGs Found in Codebase

The following inline SVGs exist in the current app and can be replaced with sprite references:

### style.css

- **Noise texture** (line 210): `data:image/svg+xml` fractal noise pattern for background texture. Decorative; not replaceable with icon sprite.
- **Horizon mask** (lines 790-791): Mask image for `.horizon::after` divider with upward notch. See `icon-horizon`.
- **Wave divider** (lines 806-807): Mask image for `header .horizon::after` with organic wave path. Decorative; custom to header.
- **Illustration masks** (lines 1430-1527): Six illustration-class masks (`.illustration-loading`, `.illustration-journey`, `.illustration-complete`, `.illustration-stars`). These are decorative compositions, not individual icons.

### app.js

- **Sparkline generator** (`makeSparkline`, line 1349): Generates inline `<svg>` polyline charts from accuracy data. See `icon-sparkline` for a static representation; the dynamic function remains in JS.
- **Toggle icons** (lines 1256-1343): Uses text characters `+` and `−` (Unicode minus) for panel expand/collapse. See `icon-plus` and `icon-minus`.

### index.html

- **HTML entities as icons**: `&rarr;` (submit button), `&larr;` (back buttons), `&times;` (close buttons). See `icon-arrow-right`, `icon-arrow-left`, and `icon-close`.
- **Favicon**: References `/static/favicon.svg` (the `漫` logotype; separate from this icon set).

---

## Design Notes

- **No rounded corners**: Matches `--radius: 0` from the app CSS tokens. Rect and polygon elements use sharp corners.
- **Stroke only**: All icons use outline/line-art style. No solid fills. This keeps them lightweight and ensures they adapt to both light and dark themes via `currentColor`.
- **Color inheritance**: Icons use `stroke="currentColor"` so they automatically pick up the text color from CSS. Use `color: var(--color-accent)` or `color: var(--color-text)` on the parent element.
- **Sizing**: Default viewBox is 24x24. Render at any size by setting `width` and `height` on the `<svg>` element.
- **Accessibility**: Use `aria-hidden="true"` on decorative icons. For interactive icons (buttons), pair with `aria-label` on the button element.
