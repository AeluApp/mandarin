# Brand Guide -- Aelu

This is the definitive brand bible for Aelu. All design decisions, marketing materials, web pages, emails, partner communications, and product interfaces derive from this document. When in doubt, this document wins.

Last updated: 2026-02-17

---

## Brand Essence

### One-line brand essence

The quiet confidence of knowing exactly where you stand in a language that once felt impossible.

This is not a tagline. It is the emotional truth underneath every screen, every drill, every diagnostic. Aelu exists so that a learner can look at their data and feel neither inflated nor deflated -- just grounded. The app is the rare space where honesty and warmth coexist without tension.

### Brand Promise

Every session leaves you measurably closer to reading, hearing, and speaking real Chinese -- and you will always know exactly how close.

This is not a feature promise. It is an experience promise. We promise that using Aelu will never feel like a waste of time, never feel dishonest about your progress, and never feel like it was designed by someone who has never studied a language.

### Brand Personality

Aelu is a person in their late thirties who has been studying something difficult for a long time and has gotten genuinely good at it -- not through talent, but through patience and honest self-assessment. They sit across from you at a wooden table in a warm, well-lit room. They do not rush. They do not flatter. When you get something wrong, they tell you clearly and without judgment. When you get something right, they nod -- not with enthusiasm, but with recognition. They never say "great job" unless they mean it. They are the kind of person who remembers your specific weaknesses from last time and has already adjusted today's plan. You trust them because they have never lied to you, not even to make you feel better.

They dress simply. They speak in short, clear sentences. They have strong opinions about pedagogy but hold them without arrogance. They think streak-based motivation is quietly corrosive. They think most learning apps are built for investors, not learners. They built something different because they were tired of the alternative.

### Emotional Territory

**Primary emotion:** Quiet competence -- the feeling of steady, unglamorous progress toward something real.

**Supporting emotions:**
- Earned clarity -- knowing exactly where your gaps are, without flinching
- Patient momentum -- the sense that today's session connects to yesterday's and tomorrow's
- Grounded warmth -- being cared for by a system that respects your intelligence

**Emotions we avoid:**
- Excitement (suggests novelty over depth)
- Urgency (suggests scarcity or manipulation)
- Guilt (streak shame, missed-day anxiety)
- Pride inflation (hollow celebration of trivial actions)
- Fun (we are not entertainment; we are training)

**The feeling after using the app:** You close the session and the screen shows you exactly what happened -- what you got right, what you missed, what shifted. You feel the same way you feel after a good workout: not euphoric, but settled. You did real work. The system noticed. Tomorrow it will adjust. That is enough.

---

## The Civic Sanctuary Aesthetic

### Philosophy

The CSS header calls this "Domestic Continuity" -- the sense that you have walked into a room that has been here for a long time and will be here after you leave. The project notes call it "Civic Sanctuary." These names describe the same idea from different angles: a space that is public but personal, built for serious use but humane in its warmth.

Civic Sanctuary is not a color palette. It is a set of design commitments:

**1. Warmth without infantilism**

The palette is built on warm stone, plaster, and earth. The background is never cold gray, never clinical white. But warmth does not mean softness: there are no rounded corners in the app (--radius: 0), no bouncy animations, no cartoon elements. The warmth comes from color temperature and typography, not from decoration.

- Right: A warm linen background (#F2EBE0) with serif typography and thin horizon-line dividers
- Wrong: Pastel colors, rounded cards, illustrated mascots, gradient buttons

**2. Calm without boredom**

The interface is restful but not lifeless. Life comes through subtle motion (upward drift on entry), texture (SVG paper-grain noise blended into the background), and typographic hierarchy (Cormorant Garamond headings have real presence). The sky gradient at the top of the page warms subtly as a session progresses. These are details you feel more than see.

- Right: A horizon line that draws itself open on page load over 0.8 seconds
- Wrong: A static page with no entrance animation at all; or a page with spinning loaders and bouncing elements

**3. Seriousness without severity**

The app treats Chinese learning as a serious project deserving of a serious tool. But serious does not mean austere. The color palette includes muted rose (accent), sage green (secondary), and warm brown undertones. These are the colors of a library reading room, not an operating theater.

- Right: Correct answers marked with a quiet sage-green left border, no confetti
- Wrong: Correct answers in bright neon green with a success animation; or correct answers with no visual acknowledgment at all

**4. Beauty without decoration**

Every visual element serves a function. The horizon line is a divider. The paper texture reduces the flatness of a solid-color screen. The accent color marks interactive elements. Nothing exists purely for ornamentation. If you removed a visual element and the interface lost information or became harder to use, it was functional. If nothing changed, it was decorative and should not have been there.

- Right: Chinese characters displayed large and centered in --font-hanzi because readability of the character *is* the function
- Wrong: A decorative Chinese calligraphy brush illustration in the header for "atmosphere"

### Design Influences

**Fisherman's Horizon (Final Fantasy VIII)**
A town built on a bridge across the ocean with no government, no military, and no conflict. Its architecture is industrial but its atmosphere is peaceful. What we take: the sense of a functional place that happens to be beautiful. No ornament, just good proportions and warm light. How it manifests: the horizon-line motif throughout the app -- thin 1px lines that divide sections like the distant ocean line. Concrete example: the `--horizon-width: 48px` dividers between header, content, and footer.

**Zeniba's cottage (Spirited Away)**
The witch's home that is the opposite of Yubaba's bathhouse -- small, warm, handmade, honest. Tea on the table. What we take: domestic scale, handmade texture, the feeling that someone who lives here also works here. How it manifests: the paper-grain SVG texture on the body background, the font choices (serif, not sans-serif), the transparent card backgrounds that let the texture show through. Concrete example: `background-blend-mode: soft-light` on the body, mixing fractal noise with the warm base color.

**Nobuo Uematsu's compositions (Final Fantasy)**
Music that is melodic and emotionally rich but never hurried. Themes that develop over minutes, not seconds. What we take: pacing and restraint. The session-start sound is a warm chime, not a fanfare. Animations take 400-500ms, not 150ms. Nothing rushes. How it manifests: the easing curves (--ease-upward: cubic-bezier(0.16, 1, 0.3, 1)) that decelerate gently into rest. Concrete example: the logo settling animation -- opacity 0 to 1 with a 4px upward drift over 1 second.

**Terrence Malick's cinematography**
Natural light, landscapes as emotional context, silence as a narrative tool. What we take: the sky gradient at the top of the page (body::before) that shifts from --color-sky-top to --color-sky-bottom, creating the sense of looking up before looking down at your work. How it manifests: environmental detail that is felt, not examined. Concrete example: the sky warms via a sepia filter as session progress increases, using the --session-progress CSS custom property.

**Your Name (Makoto Shinkai)**
Hyperreal skies and light that carry emotional weight. What we take: the dark mode palette is warm dark (#1C2028), not cold black or blue-black. The dark mode sky gradient (#222838 to #1C2028) has the quality of dusk, not void. How it manifests: dark mode feels like evening, not like a different app. Concrete example: dark mode accent shifts from #946070 (dusty rose) to #B07888 (lighter, warmer rose) for visibility without losing warmth.

**Moombas (Final Fantasy VIII)**
A village with warm earth tones, terracotta, and a relaxed pace in the middle of a tense narrative. What we take: the specific color palette of warm stone, muted rose, and sage green. How it manifests: the entire light-mode color system. Concrete example: --color-base: #F2EBE0 (warm plaster), --color-accent: #946070 (dusty rose), --color-secondary: #6A7A5A (sage).

### Design Principles (ranked by priority)

1. **Content first.** Chinese text is always the hero. Drill hanzi display at 2.074rem (--text-3xl) minimum in the app, 1.728rem (--text-2xl) on mobile. Nothing competes with the characters for visual attention.

2. **Generous whitespace.** Breathing room for learning. The app container tops out at 600px and floats centered. Section spacing uses --space-7 (3rem) and --space-8 (4rem). Cramped layouts signal rushed thinking.

3. **Warm neutrals as foundation.** The background is never cold. In light mode: #F2EBE0 (warm plaster). In dark mode: #1C2028 (warm charcoal). Pure white (#FFFFFF) appears only on primary button text. Pure black (#000000) appears nowhere.

4. **Color for meaning, not decoration.** Accent (dusty rose) marks interactive elements and the primary hanzi display. Secondary (sage) marks supporting data. Correct (muted green) and incorrect (muted brown-pink) appear only in drill feedback contexts. No color is used without semantic purpose.

5. **Motion suggests life, not demands attention.** Elements enter with subtle upward drift (translateY(6px) to 0) and fade (opacity 0 to 1). Nothing bounces, shakes, pulses to attract attention, or celebrates. All motion respects `prefers-reduced-motion: reduce`.

6. **Dark mode is warm dark, not blue-black.** The dark palette uses #1C2028 as base -- a warm, slightly blue-shifted charcoal that reads as evening. All token overrides maintain warmth: text becomes #E4DDD0 (warm cream), dividers become #3A3530 (warm umber). The dark mode is an alternate time of day, not an alternate app.

---

## Color System

**Canonical tokens (defined in BRAND.md):** base, accent, secondary, correct, incorrect, text, divider. These seven tokens and their light/dark hex values are the source of truth. All other tokens below (surface, surface-alt, text-dim, text-faint, accent-dim, border, shadow, mastery stages, sky gradients) are **derived tokens** -- implementation details in the production CSS that extend the canonical set. When a derived token conflicts with a canonical value, BRAND.md wins.

### Light Mode Palette (from style.css :root)

| Token | Hex | RGB | Usage |
|-------|-----|-----|-------|
| --color-base | #F2EBE0 | 242, 235, 224 | Page background, primary canvas |
| --color-surface | #F2EBE0 | 242, 235, 224 | Cards, panels (same as base -- continuous surface) |
| --color-surface-alt | #EAE2D6 | 234, 226, 214 | Alternate surface for depth (inputs, hover states, mastery bars) |
| --color-text | #2A3650 | 42, 54, 80 | Primary text -- warm dark navy, not pure black |
| --color-text-dim | #5A6678 | 90, 102, 120 | Secondary text -- labels, metadata, panel headings |
| --color-text-faint | #8890A0 | 136, 144, 160 | Tertiary text -- hints, timestamps, faint metadata |
| --color-accent | #946070 | 148, 96, 112 | Interactive elements: buttons, links, hanzi display, progress fill |
| --color-accent-dim | #7A5060 | 122, 80, 96 | Darker accent for borders, secondary button outlines |
| --color-secondary | #6A7A5A | 106, 122, 90 | Supporting elements: tags, warn values, loading indicators |
| --color-correct | #5A7A5A | 90, 122, 90 | Correct answer feedback (border + text) |
| --color-incorrect | #8A7068 | 138, 112, 104 | Wrong answer feedback (border + text) |
| --color-border | transparent | -- | Card borders are invisible; structure comes from dividers |
| --color-divider | #D8D0C4 | 216, 208, 196 | Horizon lines, section separators, input underlines |
| --color-shadow | rgba(42, 54, 80, 0.04) | -- | Subtle elevation for shadows (nearly invisible) |

**Mastery stage colors (light mode):**

| Token | Hex | Usage |
|-------|-----|-------|
| --color-mastery-durable | #4A6A4A | Deep green -- durable mastery |
| --color-mastery-stable | #6A8A5A | Medium green -- stable mastery |
| --color-mastery-stabilizing | #B8A050 | Warm gold -- stabilizing |

**Sky gradient (light mode):**

| Token | Hex | Usage |
|-------|-----|-------|
| --color-sky-top | #E4E0D6 | Top of the page sky gradient |
| --color-sky-bottom | #F2EBE0 | Bottom of sky gradient (blends into base) |

### Dark Mode Palette (from @media prefers-color-scheme: dark)

| Token | Hex | RGB | Usage |
|-------|-----|-----|-------|
| --color-base | #1C2028 | 28, 32, 40 | Page background -- warm charcoal |
| --color-surface | #1C2028 | 28, 32, 40 | Cards, panels (continuous surface) |
| --color-surface-alt | #242A34 | 36, 42, 52 | Alternate surface for depth |
| --color-text | #E4DDD0 | 228, 221, 208 | Primary text -- warm cream, not pure white |
| --color-text-dim | #A09888 | 160, 152, 136 | Secondary text |
| --color-text-faint | #6A6258 | 106, 98, 88 | Tertiary text |
| --color-accent | #B07888 | 176, 120, 136 | Lighter rose for dark backgrounds |
| --color-accent-dim | #946070 | 148, 96, 112 | (Same as light-mode accent) |
| --color-secondary | #8AAA7A | 138, 170, 122 | Lighter sage for dark backgrounds |
| --color-correct | #7A9A7A | 122, 154, 122 | Correct feedback (lighter for visibility) |
| --color-incorrect | #A8988E | 168, 152, 142 | Wrong feedback (lighter for visibility) |
| --color-border | transparent | -- | |
| --color-divider | #3A3530 | 58, 53, 48 | Warm umber dividers |
| --color-shadow | rgba(0, 0, 0, 0.12) | -- | Slightly stronger shadows for dark mode |

**Mastery stage colors (dark mode):**

| Token | Hex |
|-------|-----|
| --color-mastery-durable | #5A8A5A |
| --color-mastery-stable | #7AAA6A |
| --color-mastery-stabilizing | #D4B060 |

**Sky gradient (dark mode):**

| Token | Hex |
|-------|-----|
| --color-sky-top | #222838 |
| --color-sky-bottom | #1C2028 |

### Landing Page Palette Variations

The landing pages (index.html, pricing.html) use a slightly different palette that predates the app CSS refinement. These should be migrated to match the app CSS over time.

| Token | Landing Page | App CSS | Notes |
|-------|-------------|---------|-------|
| --color-base | #F5F0EB | #F2EBE0 | Landing is slightly cooler; app is warmer |
| --color-surface | #FFFBF5 | #F2EBE0 | Landing has distinct surface; app uses continuous surface |
| --color-text | #2C2C2C | #2A3650 | Landing uses near-black; app uses warm navy |
| --color-accent | #4A8B8C | #946070 | Landing uses teal; app uses dusty rose |
| --color-secondary | #946070 | #6A7A5A | Landing uses rose as secondary; app uses sage |
| --color-border | #E0D8CF | transparent | Landing has visible borders; app uses dividers only |
| --radius | 8px | 0 | Landing has rounded corners; app uses continuous surface |

**Canonical reference:** The app CSS (`mandarin/web/static/style.css`) is the source of truth. Landing pages should align to these values in future updates. The app's "continuous surface" philosophy (--radius: 0, transparent borders, horizon-line dividers) is the mature expression of the aesthetic.

### Color Usage Rules

**Accent color (dusty rose #946070 / #B07888 dark):**
- Primary CTA buttons (background)
- Active/focused input borders
- Chinese character display in drills (color)
- Progress bar fill
- Links and interactive text
- Logo mark (the character)

**Secondary color (sage #6A7A5A / #8AAA7A dark):**
- Supporting badges and tags
- Warning-level values in data panels
- Loading state indicators

**Correct/Incorrect (only in drill feedback):**
- Correct (#5A7A5A / #7A9A7A): Left border on correct answer messages, correct answer text, listening answer reveals
- Incorrect (#8A7068 / #A8988E): Left border on wrong answer messages, wrong answer text
- Never use these colors decoratively. They appear only when the learner has answered a drill.

**Text hierarchy:**
- Primary (--color-text): All body copy, headings, user-facing content
- Dim (--color-text-dim): Panel headings, labels, metadata, secondary information
- Faint (--color-text-faint): Timestamps, hints, tertiary metadata, empty state text, session info

**Background rules:**
- Never use pure white (#FFFFFF) as a background
- Never use pure black (#000000) as a background
- Both light and dark modes should feel warm -- verify by placing a swatch of #808080 (neutral gray) next to the base color; the base should read warmer

### Accessible Contrast Ratios

Key combinations tested against WCAG 2.1 standards:

| Combination | Light Mode | Dark Mode | WCAG Level |
|------------|-----------|-----------|------------|
| --color-text on --color-base | #2A3650 on #F2EBE0 = ~9.5:1 | #E4DDD0 on #1C2028 = ~11.2:1 | AAA |
| --color-text-dim on --color-base | #5A6678 on #F2EBE0 = ~5.2:1 | #A09888 on #1C2028 = ~5.8:1 | AA |
| --color-text-faint on --color-base | #8890A0 on #F2EBE0 = ~3.2:1 | #6A6258 on #1C2028 = ~3.1:1 | AA Large |
| --color-accent on --color-base | #946070 on #F2EBE0 = ~4.6:1 | #B07888 on #1C2028 = ~5.0:1 | AA |
| White on --color-accent | #FFFFFF on #946070 = ~4.5:1 | #FFFFFF on #B07888 = ~3.8:1 | AA / AA Large |
| --color-correct on --color-base | #5A7A5A on #F2EBE0 = ~4.7:1 | #7A9A7A on #1C2028 = ~5.5:1 | AA |

Notes:
- --color-text-faint is intentionally low contrast. It is used only for metadata and hints that are secondary to the learning content. At WCAG AA Large, it passes for text at 18px+ or 14px bold+. For smaller sizes, pair with --color-text-dim instead.
- White text on accent buttons in dark mode is borderline. Consider using --color-base (#1C2028) on dark mode buttons instead of #FFFFFF for stronger contrast, or ensure button text is at least 16px and 600 weight.

---

## Typography System

### Font Stack

| Role | Token | Primary Font | Fallbacks | Weights | Usage |
|------|-------|-------------|-----------|---------|-------|
| Headings | --font-heading | Cormorant Garamond | Noto Serif SC, Georgia, serif | 400, 600 | Page titles, section headers, panel headings, stat values |
| Body | --font-body | Source Serif 4 | Noto Serif SC, Georgia, serif | 400, 600 | Body text, UI labels, buttons, inputs |
| Chinese characters | --font-hanzi | Noto Serif SC | PingFang SC, Hiragino Sans GB, serif | 700 | All displayed Chinese characters (drills, reading, features) |

**Note on inline hanzi:** When Chinese characters appear inline within English body text, the CSS uses a separate treatment: `Noto Sans SC, PingFang SC, Hiragino Sans GB, sans-serif` at 0.94em with -0.04em vertical alignment. This sans-serif CJK at body size matches Source Serif 4's optical weight better than serif CJK in running text. This is specified in the `.hanzi-inline` class.

**Note on landing pages:** The pricing page uses `Source Sans 3` as primary body font with `Source Serif 4` as fallback. The app CSS uses `Source Serif 4` exclusively for body. The app CSS is canonical. Landing pages should migrate to Source Serif 4 for consistency.

### Type Scale

The type scale uses a 1.2 ratio (minor third) from a 1rem base (approximately 16px at default browser settings). The body is set at 0.95rem (15.2px) for comfortable reading density.

| Token | Size | Line Height | Usage |
|-------|------|-------------|-------|
| --text-display | 3.2rem (51.2px) | 1.1 | Session complete score, logo mark on larger screens |
| --text-3xl | 2.074rem (33.2px) | 1.2 | Drill hanzi display (primary study character) |
| --text-2xl | 1.728rem (27.6px) | 1.2 | Reading passage Chinese text, stat values on tablet+ |
| --text-xl | 1.44rem (23px) | 1.3 | Stat values, section headings, input text size |
| --text-lg | 1.2rem (19.2px) | 1.3 | Listening titles, sparklines, answer input |
| --text-base | 1rem (16px) | 1.6 | Body text, button labels, option buttons |
| --text-sm | 0.833rem (13.3px) | 1.5 | Panel headings, metadata, status bar, secondary text |
| --text-xs | 0.694rem (11.1px) | 1.4 | Legends, timestamps, shortcut buttons, badges |

### Typography Rules

1. **Chinese characters always display in --font-hanzi (Noto Serif SC).** No exceptions. If a character is meant to be read as Chinese, it uses the hanzi font stack.

2. **Never display Chinese characters below 1.2rem (19.2px) in a drill or reading context.** For metadata or labels that happen to include Chinese (e.g., a mastery bar label showing "HSK 3"), --text-sm (0.833rem / 13.3px) is acceptable because the character is not the study target.

3. **Line height for Chinese text in reading context: 2.0.** This is significantly more generous than English (1.6) because Chinese characters are visually denser and benefit from vertical breathing room. Set explicitly in `.reading-text`.

4. **Headings use sentence case.** Never ALL CAPS for headings. The `.msg-label` class uses uppercase for small functional labels (drill type indicators), but this is the only exception, and it is paired with --text-xs size and letter-spacing: 0.15em.

5. **No bold in body text unless critical emphasis.** Body weight is 400. Stat values, button text, and headings use 600. The 700 weight is reserved exclusively for Chinese characters in --font-hanzi.

6. **Pinyin displays in --font-body (Source Serif 4), not --font-hanzi.** Pinyin is romanized text and renders properly in the body font. It uses --color-text-dim for visual hierarchy below the hanzi.

7. **Letter-spacing tokens:**
   - --tracking-tight: 0.01em (stat values, timestamps, buttons)
   - --tracking-normal: 0.03em (panel headings, metadata, logo mark)
   - --tracking-wide: 0.15em (uppercase labels, logo text subtitle, hanzi display)

---

## Spacing and Layout

### Spacing Scale

The spacing system is based on an 8px (0.5rem) foundation. Tokens are numbered 1-8.

| Token | Value | Pixels (at 16px root) | Usage examples |
|-------|-------|----------------------|----------------|
| --space-1 | 0.25rem | 4px | Micro gaps: stat label margin-top, inline gaps |
| --space-2 | 0.5rem | 8px | Small gaps: input rows, shortcut button gaps, panel-body margin-top |
| --space-3 | 0.75rem | 12px | Medium-small: card padding (vertical), horizon line margins, drill group padding |
| --space-4 | 1rem | 16px | Medium: card padding (horizontal), section padding within panels, drill area padding |
| --space-5 | 1.5rem | 24px | Medium-large: app side padding, header padding, mastery bar section padding, stat row margins |
| --space-6 | 2rem | 32px | Large: app top padding (mobile/tablet), header bottom padding, complete section padding |
| --space-7 | 3rem | 48px | Section separation: action buttons margin, stat row bottom margin |
| --space-8 | 4rem | 64px | Major section separation: app top padding (desktop), complete section top padding |

### Layout Principles

**Maximum content width:** 600px for the app interface (`#app { max-width: 600px }`). Landing pages use 720px for body content (`.container`) and 960px for wider grids (`.container-wide`).

**Card padding:** `var(--space-3) var(--space-4)` = 12px vertical, 16px horizontal. This is set as `--card-padding` and used by `.stat`, `.panel`, and similar components.

**Panel padding:** Same as card padding: `var(--space-3) var(--space-4)`.

**Button padding:** Primary buttons: `14px 32px` (--btn-padding). Secondary buttons: `14px 24px`. Minimum touch target: 44px x 44px on both buttons and interactive elements (per WCAG 2.5.5).

**Section spacing:** Panels within `.panels-group` are separated by --space-1 (4px) margin. On tablet+ (768px), panels display in a 2-column grid with --space-2 (8px) gap.

**Border radius:** 0 everywhere in the app (`--radius: 0`). This is the "continuous surface" principle -- no rounded corners, no card edges. Structure comes from horizon-line dividers (1px solid --color-divider) rather than card boundaries. Landing pages currently use 8px radius; this should migrate to 0 over time.

**Mobile breakpoints:**
- 360px and below: Small phones -- reduced padding, smaller logo, stacked action buttons
- 480px and below: Standard phones -- sticky bottom input area, reduced hanzi size
- 600px and above: Large phones / small tablets -- stats row no-wrap
- 768px and above: Tablets -- 2-column panel grid, larger type sizes
- Landscape under 500px height: Compressed vertical spacing

**Grid system:** CSS Grid is used for feature cards (2-column on desktop, 1-column on mobile) and panel groups (2-column on tablet+). Flexbox is used for stat rows, action buttons, input rows, and mastery bar rows. No external grid framework.

---

## Motion and Animation

### Animation Principles

1. All animation serves a purpose: entrance transition, state change feedback, or ambient environmental detail.
2. Nothing animates to demand attention. No bounce, no shake, no pulse on interactive elements (the only pulse is the WebSocket loading dot, which is a status indicator, not a call to action).
3. All animations respect `prefers-reduced-motion: reduce` via a media query that sets all animation-duration and transition-duration to 0.01ms.
4. Entrances use ease-out (decelerate into rest). Exits use ease-in (accelerate out of view). This is physics: things arriving slow down; things leaving speed up.

### Duration Tokens

| Token | Value | Usage |
|-------|-------|-------|
| --duration-press | 0.1s | Button press feedback (scale 0.98) -- near-instant |
| --duration-fast | 0.2s | Micro-interactions: hover states, tooltip show/hide, input focus |
| --duration-base | 0.4s | Standard transitions: drill message entrance, section enter |
| --duration-slow | 0.5s | Larger transitions: hanzi reveal, mastery bar width, progress fill, panel collapse |
| --duration-ambient | 1.8s | Ambient loops: loading dot pulse |
| --duration-float | 3s | Illustration hover float (subtle 2px vertical oscillation) |

### Easing Curves

| Token | Value | Character |
|-------|-------|-----------|
| --ease-default | cubic-bezier(0.25, 0.1, 0.25, 1) | General-purpose smooth easing |
| --ease-upward | cubic-bezier(0.16, 1, 0.3, 1) | Entrance easing -- strong deceleration, elements settle into place |
| --ease-overshoot | cubic-bezier(0.34, 1.56, 0.64, 1) | Slight overshoot -- used sparingly, for elements that need to "land" |
| --ease-exit | cubic-bezier(0.4, 0, 1, 1) | Exit easing (ease-in) -- elements accelerate out of view |

### Defined Animations

**driftUp** -- The signature entrance animation.
- From: opacity 0, translateY(6px)
- To: opacity 1, translateY(0)
- Duration: --duration-base (0.4s) with --ease-upward
- Used for: Drill messages, input area, session content, reading passages, media cards

**logoSettle** -- Header logo entrance.
- From: opacity 0, translateY(4px)
- To: opacity 1, translateY(0)
- Duration: 1s with --ease-upward
- Staggered: logo mark (0s), logo text (0.15s), session info (0.4s)

**horizonDraw** -- Horizon line entrance.
- From: width 0, opacity 0
- To: width --horizon-width (48px), opacity 1
- Duration: 0.8s with --ease-upward, delay 0.3s

**hanziReveal** -- Chinese character entrance in drills.
- From: opacity 0
- To: opacity 1
- Duration: --duration-slow (0.5s) with --ease-upward, delay 0.1s

**feedbackIn** -- Correct/incorrect answer feedback.
- From: opacity 0, translateX(-4px)
- To: opacity 1, translateX(0)
- Duration: --duration-fast (0.2s) with --ease-upward

**sectionEnter** -- Major section transitions (dashboard to session, session to complete).
- From: opacity 0, translateY(12px)
- To: opacity 1, translateY(0)
- Duration: --duration-base (0.4s) with --ease-upward

**sectionExit** -- The counterpart.
- To: opacity 0, translateY(-6px)
- Uses --ease-exit (accelerate out)

**barFadeIn** -- Mastery bar segments entrance.
- From: opacity 0
- To: opacity 1
- Duration: --duration-slow (0.5s)
- Staggered: each segment delayed by 0.06s

**underlineGrow** -- Completion heading underline.
- From: width 0, left 50%
- To: width 100%, left 0
- Duration: 1.2s with --ease-upward, delay 0.3s

**ringSettle** -- Score completion ring.
- From: opacity 0, scale 0.8
- Through: opacity 0.6 at 60%
- To: opacity 0.3, scale 1
- Duration: 1.6s with --ease-upward, delay 0.4s

**No animation applied to:**
- Drill text the user is actively reading or working with
- Input fields while the user is typing
- Data in panels and tables (enters via content crossfade, a simple fast fade)
- Anything during prefers-reduced-motion: reduce

---

## Sound Design

### Web Audio API Sounds

**Session start:** A warm, brief tone. Designed to signal "we are beginning" without demanding attention. Think of a single note on a vibraphone, sustained for one second, with natural decay. Not a chime sequence, not a melody -- a single resonant note.

**Session complete:** A satisfying resolution. Slightly richer than the start sound -- possibly two tones a fifth apart, gently overlapping. The feeling of setting something down, not of winning something. Duration: 1.5-2 seconds including decay.

**Correct answer:** Silent. The visual feedback (sage-green left border, color shift) is sufficient. Adding sound to every correct answer would create Pavlovian anxiety about the sound not playing on wrong answers.

**Wrong answer:** Silent. Same reasoning. The visual feedback (muted brown-pink left border) communicates clearly without audio punishment.

**Navigation, scrolling, feature discovery:** No sound.

### Sound Principles

1. Sound is off by default. The user opts in via a sound toggle in the status bar.
2. Never startling. Maximum volume is moderate; sounds use gradual attack, not sharp onset.
3. Warm, natural timbres. No 8-bit sounds, no synthetic chirps, no notification-style pings. Think: a single piano note heard from two rooms away.
4. Sound should feel like it belongs in a library reading room. If the sound would cause someone at an adjacent table to look up, it is too prominent.
5. Sound serves as temporal punctuation -- "this phase has begun," "this phase has ended" -- not as reward or punishment.

---

## Iconography and Imagery

### Icon Style

The app currently uses minimal iconography -- most UI is text-based. Where icons appear:

- Line-based, not filled
- Monochrome (--color-text-faint or --color-accent)
- Implemented as inline SVG masks using `mask-image` for automatic theme adaptation
- No emoji as functional icons

The illustration vocabulary defined in the CSS uses SVG mask images for thematic vignettes:

| Illustration | Elements | Context |
|-------------|----------|---------|
| Empty state | Horizon line + sun circle | Waiting/empty states, no data |
| Loading | Horizon line + cloud wisps | Preparing state, data loading |
| Journey | Horizon line + bird (chevron) | Session in progress |
| Complete | Horizon line + settling sun | Session complete, arrival |
| Stars | Horizon line + dots | Streak/consistency, time passage |

All illustrations are 80x40px or 120x32px, rendered in --color-illustration (which maps to --color-divider), at reduced opacity (0.3-0.5). They are meant to be noticed subconsciously, not examined.

### Photography and Illustration Direction

- **If using photos:** Warm-toned, natural light, calm settings -- libraries, wooden desks, cafe tables, study corners. Never stock-photo-perfect. Real environments with real imperfections. Never photos of people "studying" with exaggerated expressions.
- **If using illustrations:** Minimal, line-based, warm palette. Not cartoon, not corporate. Consistent with the SVG mask illustration vocabulary already in the CSS.
- **Chinese cultural imagery:** Respectful, contemporary, not stereotypical. No dragons, no red lanterns, no Great Wall, no calligraphy brushes used as decoration. Chinese characters themselves are the primary cultural visual element, and they are displayed with typographic care (Noto Serif SC at generous size), not as decoration.

### Screenshot Style

- Browser chrome visible (establishes the "web app" context)
- Warm background behind the browser window -- use --color-surface-alt or a slightly desaturated version, not plain gray
- Feature callouts use --color-accent, not red circles or neon arrows
- Always produce dark mode and light mode versions of every screenshot
- Screenshots should show real data states (real scores, real Chinese characters, real drill types), not placeholder content

---

## Logo and Wordmark

### Current State

The app uses a two-part logo composition:

1. **Logo mark:** The character (man, "flowing/rambling" -- the first character of manhua, manga, etc.) displayed in --font-hanzi at --text-display size (3.2rem), weight 700, color --color-accent. It settles into place with the logoSettle animation.

2. **Logo text:** "Aelu" displayed in --font-heading (Cormorant Garamond) at --text-base (1rem), weight 400, color --color-text-dim, with --tracking-wide (0.15em) letter spacing.

3. **Horizon line:** A 48px wide, 1px tall line in --color-divider centered below the text, animating in with horizonDraw.

These three elements together form the complete logo. They are always stacked vertically, always centered.

### Wordmark Specification

- "Aelu" set in Cormorant Garamond at 400 weight
- Letter-spacing: 0.15em
- Color: --color-text-dim on light backgrounds (#5A6678); --color-text-dim on dark backgrounds (#A09888)
- Minimum display size: 14px (below this, the letter-spacing and thin serifs become illegible)
- Clear space: At minimum, --space-3 (12px) on all sides
- The wordmark is always lowercase-initial: "Aelu" -- never "AELU," never "aelu"

**Do not:**
- Stretch, compress, or rotate the wordmark
- Add drop shadows, outlines, or glow effects
- Change the font or weight
- Place on a busy or photographic background without a solid-color backing
- Separate the wordmark from the character mark when used as the full logo

### App Icon Concept Directions

No app icon currently exists. When created, it should embody Civic Sanctuary. Four concept directions:

1. **The character** -- simplified to work at small sizes, rendered in --color-accent on --color-base. The character itself is distinctive and recognizable even at 16px if simplified to its essential strokes.

2. **Horizon mark** -- a minimal geometric abstraction of the horizon-line motif: a thin horizontal line with a small circle (sun) partially visible above it. Rendered in --color-accent. Captures the environmental quality of the aesthetic.

3. **Passage mark** -- a vertical rectangle (book/passage reference) with a single horizontal line inside (the horizon). Combines the reading emphasis with the environmental motif.

4. **Character fragment** -- a single radical or stroke from a Chinese character, abstracted to the point of being a geometric mark. The (water radical) from would work: three flowing strokes that read as both Chinese calligraphy and abstract form.

Color: --color-accent on --color-base in both light and dark modes.
Must be legible at 16x16px (favicon), 32x32px (tab icon), 180x180px (Apple touch), and 512x512px (app store).

### Favicon

- 32x32px and 16x16px versions
- Simplified to essential form -- likely one of the icon concepts above at maximum reduction
- Must be recognizable in a browser tab among dozens of other tabs
- Test against both light and dark browser chrome

---

## Brand Applications

### Web App

**Dashboard:** The brand shows up through the warm plaster background, the generous stat layout with Cormorant Garamond numerals in accent color, and the mastery bars using the earth-toned stage colors. Panels have no borders -- only horizon-line dividers at the top. The overall feeling is a well-organized desk, not a dashboard.

**Drill interface:** The brand is most visible here. Chinese characters dominate the center of the screen at --text-3xl in --font-hanzi, colored in --color-accent, bounded by thin horizon dividers above and below. The input area sits at the bottom with a simple underline (not a bordered box). Feedback appears as a left-bordered message (green for correct, brown-pink for incorrect) that drifts in from the left. Past drills fade to 40% opacity. The feeling is focused, uncluttered, and respectful of the cognitive work happening.

**Reading view:** Chinese text displays at --text-2xl with line-height 2.0 on a --color-surface-alt background. Words are tappable with a subtle dotted underline on hover and a 12% accent color wash. The reading gloss (popup definition) appears as a small fixed-position panel with the base background color and a divider border. The feeling is a physical book with margin annotations.

**Session complete:** The score displays at --text-display with a thin settling circle behind it (1px border, 30% opacity). A curved horizon arc appears above the completion content. The session narrative and details are presented in quiet, factual typography. No confetti, no celebration animation, no "great job." The feeling is setting down a finished document.

### Landing Pages

**Hero pattern:** Centered text. A large Chinese phrase in --font-hanzi at the top (decorative but real Chinese -- currently "learn and practice regularly"). H1 in Cormorant Garamond at 2.8rem. Subtitle in body font at muted color. Email signup form below. No hero image, no illustration, no background photo. The Chinese characters *are* the visual.

**Section pattern:** Alternating between full-width sections with --color-surface background (problem statement, how-it-works, FAQ) and open sections on --color-base. Sections are separated by 1px borders, not by background color alone. Each section has an h2 in Cormorant Garamond at 1.8rem, centered.

**CTA pattern:** Primary button in --color-accent with light-colored text, 8px border radius (landing page legacy -- should migrate to 0). "Get early access" or "Get Full Access" -- specific verbs, no exclamation marks. Secondary button is transparent with accent-colored border and text.

**Footer pattern:** Centered, small text (0.85rem) in --color-text-faint. Navigation links underlined. Copyright line. Minimal, not sticky, not elaborate.

### Email

- Emails should feel like a personal letter, not a marketing template
- No heavy HTML -- minimal formatting, no header images, no multi-column layouts
- From name: "Aelu" (not "Aelu Team," not "Aelu App")
- Font: System fonts only (email clients cannot reliably load custom fonts) -- use `Georgia, 'Times New Roman', serif` as the closest system match to Source Serif 4
- Links in a muted rose color (approximate --color-accent #946070 in email-safe hex)
- Sign-off: "-- Aelu," no title, no signature block logo
- Maximum one CTA per email, and it should be a text link, not a styled button
- Line length: aim for 60-70 characters per line for readability

### Social Media

- Profile images: The character on --color-base background, or the wordmark centered on --color-base
- Post images: Warm --color-base backgrounds, large Chinese text in --font-hanzi (or system serif if font loading is unavailable), minimal English copy
- Share real learning data, real drill examples, real progress screenshots -- not mockups or idealized states
- Never: memes, trendy formats, "like and share," clickbait headlines, engagement bait
- Tone matches the brand voice: calm, direct, grounded. A social post reads like a note from someone who built something and wants to share what they learned, not like a brand account performing relatability.

### Presentation / Pitch Deck

- Warm backgrounds (--color-base or --color-surface-alt)
- Large type (Cormorant Garamond for headings, Source Serif 4 for body)
- Minimal slides -- more whitespace, fewer words
- Chinese character examples as visual centerpieces (a single character at 120px+ is more compelling than a feature list)
- Data presented cleanly: tables with thin borders, no 3D charts, no pie charts
- No clip art, no stock photos of "diverse teams brainstorming," no generic "person using laptop" imagery
- If showing the app, use real screenshots with real data, in both light and dark mode

---

## Brand Voice Reference

The full voice and tone guidelines live in `marketing/positioning.md`. This section summarizes the key rules for quick reference.

### Voice Character

**Direct.** Short sentences. No hedging. "Your listening is behind your reading" -- not "You might want to consider focusing a bit more on listening skills."

**Grounded.** Every claim backed by a specific feature, research finding, or data point. "27 drill types" is grounded. "Revolutionary learning experience" is not.

**Calm.** No urgency, no anxiety, no FOMO. No exclamation marks in product UI. The tone is a knowledgeable peer, not a salesperson.

**Respectful.** Assumes the reader is intelligent and has done their research. Does not over-explain.

### Key Rules

- Never use exclamation marks in product UI
- Never use emoji in official communications
- Never capitalize for emphasis (use italics sparingly, or restructure the sentence)
- Use "drill" not "exercise," "session" not "lesson," "diagnostics" not "insights"
- The full words-we-use / words-we-avoid table is in positioning.md

---

## Brand Don'ts

### Visual

- Never use gradients (except the environmental sky gradient, which is a fixed design element, not a decorative choice)
- Never use drop shadows heavier than --shadow-md (0 2px 6px rgba(42, 54, 80, 0.04))
- Never use stock photography of people "studying"
- Never use neon or highly saturated colors
- Never use more than two accent colors on a single page
- Never put text over busy images or photographic backgrounds
- Never use decorative dividers -- the only divider is the 1px horizon line in --color-divider
- Never use rounded corners in the app interface (--radius: 0)
- Never use card borders in the app interface (--color-border: transparent)
- Never use background colors to create card boundaries (use horizon-line dividers instead)

### Verbal

- Never use exclamation marks in product UI or feature descriptions
- Never use emoji in official communications
- Never capitalize for emphasis
- Never use "AI-powered," "smart," "revolutionary," "game-changing," "fun way to learn"
- Never use "journey," "ecosystem," "all-in-one," "comprehensive"
- Never praise trivially -- "Good job" is never appropriate for opening the app, completing a single drill, or maintaining a streak

### Behavioral

- Never send more than two emails per week to any user
- Never show a popup within 30 seconds of page load
- Never auto-play audio or video
- Never dark-pattern the cancellation flow -- cancellation should be as easy as signup
- Never celebrate trivial actions ("You opened the app," "You completed 1 drill")
- Never weaponize streaks ("You are about to lose your streak," "Don't break your streak")
- Never send push notifications that create guilt or urgency
- Never ask for an app store review during a drill session
- Never gate previously accessible content behind a paywall
- Never show ads

---

## Brand Audit Checklist

Use this checklist when reviewing any new page, email, feature, or design asset.

**Color and Theme:**
- [ ] Colors match the documented palette -- no rogue hex codes
- [ ] Light mode background is warm (#F2EBE0 or --color-base), never cold gray or pure white
- [ ] Dark mode exists and uses the warm dark palette (#1C2028 base)
- [ ] Dark mode respects prefers-color-scheme and/or data-theme attribute
- [ ] Accent color is used only for interactive elements and primary hanzi, not decoratively
- [ ] Correct/incorrect colors appear only in drill feedback contexts

**Typography:**
- [ ] Typography uses the correct font stack (Cormorant Garamond headings, Source Serif 4 body, Noto Serif SC hanzi)
- [ ] Chinese characters display in Noto Serif SC at 700 weight
- [ ] Chinese characters in drill/reading context are at least 1.2rem
- [ ] Line height for Chinese reading text is 2.0
- [ ] Headings use sentence case, not ALL CAPS (except small functional labels)
- [ ] Pinyin uses --font-body, not --font-hanzi

**Spacing and Layout:**
- [ ] Spacing follows the documented scale (multiples of --space tokens)
- [ ] Maximum content width respects 600px (app) or 720px/960px (landing pages)
- [ ] Touch targets are at least 44px x 44px
- [ ] Mobile responsive at 360px, 480px, 600px, and 768px breakpoints

**Animation:**
- [ ] Animation respects prefers-reduced-motion: reduce
- [ ] No bounce, shake, or pulse animations on interactive elements
- [ ] Entrance animations use --ease-upward (decelerate in)
- [ ] Exit animations use --ease-exit (accelerate out)
- [ ] Durations fall within documented ranges (0.1s-0.5s for interactions, up to 1.8s for ambient)

**Voice and Copy:**
- [ ] Copy matches brand voice: calm, direct, honest, grounded
- [ ] No exclamation marks in UI text
- [ ] No dark patterns or guilt-based language
- [ ] Brand voice: calm, direct, personal
- [ ] Specific verbs in CTAs ("Start a session" not "Get started")
- [ ] Uses preferred vocabulary (drill, session, diagnostics -- not exercise, lesson, insights)

**Accessibility:**
- [ ] Accessible contrast ratios met (WCAG AA minimum for all text)
- [ ] Focus states visible (2px solid --focus-ring-color outline)
- [ ] Skip link present on pages with navigation
- [ ] Screen reader text (.sr-only) provided where visual-only information exists
- [ ] ARIA labels on form inputs and interactive elements

**Integrity:**
- [ ] No stock photography
- [ ] No emoji used as functional icons
- [ ] No auto-playing media
- [ ] No popups within 30 seconds of page load
- [ ] Cancellation flow is straightforward
- [ ] Data claims are accurate and verifiable
