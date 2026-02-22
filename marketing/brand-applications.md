# Brand Applications — Mandarin

This document specifies how to apply the brand consistently across every touchpoint. Reference BRAND.md for the underlying identity system and positioning.md for voice and messaging. This document covers practical application — dimensions, colors, fonts, spacing — so that anyone can create on-brand assets without guessing.

All color values are extracted from the production CSS (`mandarin/web/static/style.css`). When this document says "warm stone" or "base color," it means the specific hex listed.

---

## Color Reference (from CSS)

Use these exact values. Do not approximate.

| Token | Light Mode | Dark Mode | Description |
|-------|-----------|-----------|-------------|
| --color-base | #F2EBE0 | #1C2028 | Warm linen background / deep indigo |
| --color-surface | #F2EBE0 | #1C2028 | Same as base (continuous surface) |
| --color-surface-alt | #EAE2D6 | #242A34 | Slightly darker surface variant |
| --color-text | #2A3650 | #E4DDD0 | Coastal indigo / warm cream |
| --color-text-dim | #5A6678 | #A09888 | Secondary text |
| --color-text-faint | #8890A0 | #6A6258 | Tertiary text, labels |
| --color-accent | #946070 | #B07888 | Bougainvillea rose — primary action, emphasis |
| --color-accent-dim | #7A5060 | #946070 | Darker rose — borders, secondary accent |
| --color-secondary | #6A7A5A | #8AAA7A | Cypress olive — positive secondary |
| --color-correct | #5A7A5A | #7A9A7A | Sage green — earned, not celebrated |
| --color-incorrect | #8A7068 | #A8988E | Warm brown — not red, not alarm |
| --color-divider | #D8D0C4 | #3A3530 | Horizon lines |

**For all external assets (social, email, print, slides), use light mode values unless creating a dark-specific variant.** Light mode is the canonical palette.

## Font Reference (from CSS)

| Token | Stack | Usage |
|-------|-------|-------|
| --font-heading | Cormorant Garamond, Noto Serif SC, Georgia, serif | Headlines, display text, navigation labels |
| --font-body | Source Serif 4, Noto Serif SC, Georgia, serif | Body copy, UI text, descriptions |
| --font-hanzi | Noto Serif SC, PingFang SC, Hiragino Sans GB, serif | Chinese characters (standalone, featured) |

Note: The app uses Source Serif 4 for body text, not Source Sans 3. All external assets should match the production typefaces. If Source Serif 4 is unavailable in a design tool, Georgia is the approved fallback. Never use a sans-serif font for body text in Mandarin brand materials.

---

## Social Media Assets

### Profile Images

All profile images use the same core design: the wordmark "Mandarin" set in Cormorant Garamond on the base color background.

| Platform | Dimensions | Content | Notes |
|----------|-----------|---------|-------|
| Twitter/X | 400x400px | Wordmark "Mandarin" centered | Cormorant Garamond 48pt, color #2A3650, bg #F2EBE0 |
| LinkedIn | 400x400px | Same as Twitter | Identical file |
| Instagram | 320x320px | Wordmark "Mandarin" centered | Cormorant Garamond 40pt (slightly larger relative to canvas for legibility at small sizes) |
| Discord | 512x512px | Wordmark "Mandarin" centered | Cormorant Garamond 56pt |
| YouTube | 800x800px | Wordmark "Mandarin" centered | Cormorant Garamond 80pt |
| Favicon | 32x32px + 16x16px | The mark character 漫 | Noto Serif SC Bold, color #946070, bg #F2EBE0. Must be legible at 16px — test at actual size before committing |

**Profile image specifications:**

- Background: solid #F2EBE0 (no texture, no gradient — profile images are too small for subtlety)
- Text: #2A3650 (--color-text light)
- Vertical alignment: center the text optically, not mathematically — the descender on "d" in "Mandarin" pulls the visual center down, so shift the text block up ~2% of canvas height
- No border, no circle crop styling (platforms handle this)
- Export as PNG with transparency off

**What NOT to include in profile images:**
- No tagline (too small to read)
- No Chinese characters alongside the wordmark (visual clutter at small sizes)
- No accent color (the rose reads as pink at thumbnail size and changes the brand feel)
- No icon or logomark separate from the text

### Cover / Banner Images

All banners use the same visual concept adapted to each platform's dimensions: warm linen background with the brand's horizon-line motif, tagline in Cormorant Garamond, and a single thin accent line in bougainvillea rose.

| Platform | Dimensions | Safe Area |
|----------|-----------|-----------|
| Twitter/X | 1500x500px | Central 1500x320px (top/bottom may be cropped by profile photo overlay) |
| LinkedIn | 1584x396px | Central 1584x280px (bottom 116px overlapped by profile card) |
| YouTube | 2560x1440px | TV: full 2560x1440. Desktop: 2560x423 centered. Mobile: 1546x423 centered. Keep all text within 1546x423. |
| Discord | 960x540px | Full area usable |

**Banner layout (all platforms):**

1. Background: solid #F2EBE0. No texture (SVG noise does not survive JPEG compression at social media resolutions).
2. A single 1px horizontal line in #D8D0C4 (--color-divider) spanning the center 60% of the canvas width, vertically centered. This is the horizon-line motif.
3. Tagline "Every word you look up becomes practice." set in Cormorant Garamond, 24-36pt depending on canvas size, color #2A3650, centered above the horizon line with 16px gap.
4. A short (48px wide) horizontal accent bar in #946070 (--color-accent) positioned 12px below the horizon line, centered. This is the brand's visual signature — it echoes the horizon-line dividers in the app.
5. No wordmark on the banner (the profile image already says "Mandarin" and sits next to the banner on every platform).

**Platform-specific adjustments:**
- Twitter/X: Tagline at 28pt. Horizon line at vertical center of safe area (y=160px from top).
- LinkedIn: Tagline at 24pt. Everything shifted up 40px from true center to account for the profile card overlap.
- YouTube: Tagline at 36pt (large canvas). All elements within the 1546x423 mobile safe area. Test at mobile crop before publishing.
- Discord: Tagline at 24pt. Can optionally include "mandarinapp.com" in Source Serif 4 12pt, color #8890A0, bottom-right corner with 16px margin.

**What NOT to include in banners:**
- No screenshots or app UI
- No Chinese characters (the banner is not a teaching surface)
- No dark mode variant (light is the canonical external presentation)
- No photographs or illustrations beyond the horizon-line motif
- No gradient backgrounds

### Post Templates

#### Single-Image Post (Instagram, Twitter, LinkedIn)

Two formats: 1080x1080px (square, preferred for Instagram) and 1200x628px (landscape, preferred for Twitter/LinkedIn link cards).

**Layout 1 — Chinese character focus**

Purpose: Vocabulary teaching, word of the day, interesting character breakdowns.

- Background: #F2EBE0 (solid)
- Chinese character: Noto Serif SC Bold, 120pt for square / 96pt for landscape. Color #946070 (--color-accent). Centered horizontally, positioned at 35% from top (upper third, not dead center — gives the character visual weight and room for the supporting text below).
- Pinyin: Source Serif 4, 28pt, color #5A6678 (--color-text-dim). Centered, 16px below the character. Tone marks, never tone numbers.
- English meaning: Source Serif 4, 22pt, color #8890A0 (--color-text-faint). Centered, 12px below pinyin.
- Horizon line: 1px, #D8D0C4, 48px wide, centered, 24px below the English text.
- Wordmark "Mandarin": Cormorant Garamond, 14pt, color #8890A0, bottom-right corner, 24px margin from edges.

Example content for 学 (xue):
```
学
xue
to study; to learn
─
                                          Mandarin
```

**Layout 2 — Study tip**

Purpose: Learning advice, grammar explanations, method discussions.

- Background: #F2EBE0 (solid)
- Accent bar: 3px tall, full width of text block (padded 80px from left edge), #946070, positioned 60px from top.
- Headline: Cormorant Garamond, 36pt, color #2A3650. Left-aligned, 80px from left edge, 24px below accent bar. Maximum 2 lines.
- Body text: Source Serif 4, 18pt, color #5A6678, line-height 1.6. Left-aligned, 80px from left edge, 16px below headline. Maximum 4 lines for square, 3 for landscape.
- Wordmark: Cormorant Garamond, 14pt, color #8890A0, bottom-right, 24px margin.
- Right margin: 80px (generous whitespace — never let text approach the edge).

**Layout 3 — Data / statistic**

Purpose: Interesting numbers, research findings, app milestones.

- Background: #F2EBE0 (solid)
- Large number: Cormorant Garamond, 96pt, color #946070. Centered, positioned at 30% from top.
- Context label: Source Serif 4, 20pt, color #2A3650. Centered, 12px below number. One line, maximum 40 characters.
- Supporting detail: Source Serif 4, 16pt, color #5A6678. Centered, 8px below context label. One line.
- Wordmark: bottom-right, same spec as other layouts.

Example: "27" / "drill types across 6 skill categories" / "recognition, production, listening, speaking, tone, register"

**Layout 4 — Quote / insight**

Purpose: Observations from the learning experience, quotes from research, user comments.

- Background: #F2EBE0 (solid)
- Left border: 2px solid #946070, full height of quote text, positioned 80px from left edge.
- Quote text: Cormorant Garamond Italic, 28pt, color #2A3650. Left-aligned, 96px from left edge (16px indent from the border), 200px from top (vertically centered). Maximum 4 lines.
- Attribution: Source Serif 4, 16pt, color #8890A0. Left-aligned with quote text, 16px below quote. Format: "— after session 247" or "— Pimsleur, 1967"
- No quotation marks (the border does the work).
- Wordmark: bottom-right, same spec.

#### Carousel Post (Instagram)

1080x1080px per slide. 4-6 slides total (never more than 7).

**Slide 1 — Hook:**
- Background: #F2EBE0
- Large text: Cormorant Garamond, 48pt, color #2A3650. Centered. A question or provocative statement (e.g., "Why does your vocabulary feel bigger than your reading?"). Maximum 3 lines.
- Small text below: Source Serif 4, 16pt, color #8890A0: "Swipe for the answer."
- No wordmark on slide 1 (it is a hook, not a billboard).

**Slides 2-5 — Content:**
- Alternate backgrounds between #F2EBE0 and #EAE2D6 (--color-surface-alt). This creates visual rhythm without introducing new colors.
- One point per slide. Heading in Cormorant Garamond 32pt, color #2A3650. Body in Source Serif 4 18pt, color #5A6678. Left-aligned, 80px margins.
- If a slide includes a Chinese example: Noto Serif SC Bold, 64pt, #946070, centered above the explanation text.
- Accent bar (3px, #946070) at the top of each slide as a consistent element.
- Generous whitespace. If the text fills more than 50% of the slide, split it across two slides.

**Final slide — CTA:**
- Background: #F2EBE0
- "Mandarin" in Cormorant Garamond 36pt, color #2A3650, centered.
- Tagline below in Source Serif 4 18pt, color #5A6678.
- "Free for HSK 1-2. mandarinapp.com" in Source Serif 4 16pt, color #8890A0, centered below tagline.
- Horizon line (48px, #D8D0C4) between wordmark and tagline.

#### Story / Reel Template (Instagram, TikTok)

1080x1920px.

- Text placement: upper third of the frame (y: 200-640px). This avoids the platform UI elements (status bar at top, interaction buttons at bottom right on TikTok, swipe-up area at bottom on Instagram).
- Background: solid #F2EBE0 or a blurred screenshot of the app at 40% opacity over #F2EBE0. Never a raw screenshot — always blurred or dimmed so text is readable.
- Text: Source Serif 4 Bold, 36pt minimum for primary text. Color #2A3650. Never smaller than 28pt for any text on screen (stories are viewed on phones at arm's length).
- Chinese characters: Noto Serif SC Bold, 72pt minimum, color #946070. Always centered.
- Pinyin: Source Serif 4, 24pt, color #5A6678, centered below character.
- No complex animations. Acceptable motion: simple cuts between cards, fade-in (0.3s), upward drift (translateY 8px to 0, 0.4s). No zooms, no spins, no bounces.
- Wordmark at bottom: Cormorant Garamond, 18pt, color #8890A0, centered, 120px from bottom edge.

---

## Email Design

### Email Template Specification

Email clients cannot reliably load web fonts. All email typography must use system fallback stacks.

**Typography:**
- Heading fallback (for Cormorant Garamond): `Georgia, "Times New Roman", serif`
- Body fallback (for Source Serif 4): `Georgia, "Times New Roman", serif` (Source Serif 4 is also a serif, so Georgia is the closest widely available match. Do not use a sans-serif fallback.)
- Chinese text fallback: `"PingFang SC", "Microsoft YaHei", "Noto Sans SC", "Hiragino Sans GB", sans-serif`

**Layout:**
- Max width: 600px, centered
- Background: #F5F0EB (slightly warmer than #F2EBE0 to compensate for how email clients render backgrounds — test in Gmail, Apple Mail, and Outlook)
- Text color: #2A3650
- Link color: #946070 (--color-accent). Underlined on hover only.
- Padding: 24px left/right, 32px top/bottom
- No header image. The email should feel like a personal letter, not a newsletter. Start with text.
- From name: "Mandarin" for all communications. Consistent, brand-centric, no personal attribution needed.
- Footer: "Mandarin" wordmark in Georgia 14pt, color #8890A0. Below that: unsubscribe link, mailing address (required by CAN-SPAM). No social media icons.

**Section patterns:**

*Progress report block:*
```
Vocabulary       HSK 3 (72% ready)
Listening        HSK 2 (89% ready)
Reading          HSK 3 (61% ready)
Tones            HSK 2 (94% ready)
──────────────────────────────────
Sessions this week: 5
Average accuracy:   78%
```

- Left column: stat labels in Georgia 14pt, color #5A6678
- Right column: values in Georgia 14pt Bold, color #2A3650, right-aligned
- Horizontal rule: 1px solid #D8D0C4
- Layout: HTML table (the only reliable way to get left-right alignment in email). No CSS grid, no flexbox.
- The feel should be a receipt or a library catalog card, not a dashboard.

*CTA button:*
- Dimensions: auto width (min 200px), 48px height
- Background: #946070 (--color-accent)
- Text: #FFFFFF, Georgia Bold 16pt, centered
- Border-radius: 0 (matching the app's radius-zero aesthetic)
- Border: none
- Padding: 14px 32px
- One CTA per email, maximum. If the email has no clear action, omit the button entirely.

*Chinese text inline:*
- Font: PingFang SC or system Chinese font
- Size: 1.2x the surrounding English text size (if body is 16px, Chinese is 19px)
- Color: #946070 (accent) for featured vocabulary, #2A3650 (text) for inline mentions
- Always follow Chinese characters with pinyin in parentheses for email context (readers may be on systems without Chinese font support): 学 (xue, to study)

---

## App Store / Web Store Assets

### App Icon

1024x1024px master file. iOS requires this at 1024x1024 and generates all smaller sizes. Android requires adaptive icon format (108dp with safe zone).

**Design constraints:**
- Must be legible at 29x29px (smallest iOS home screen size on older devices)
- No text (unreadable at small sizes)
- Flat design — no gradients, no 3D effects, no shadows, no gloss
- Background: #F2EBE0 (--color-base light)
- Foreground element: single shape in #946070 (--color-accent)

**Concept direction 1 — The character 漫:**
The brand mark 漫 (man, drifting/wandering) rendered in Noto Serif SC Bold, centered, color #946070 on #F2EBE0 background. At 29px this becomes an abstract shape, which is acceptable — the character is recognizable to Chinese readers and reads as a distinctive mark to everyone else. Scale the character to fill ~65% of the icon area.

**Concept direction 2 — Horizon and sun:**
The app's signature illustration motif — a thin horizontal line with a small circle (sun) above it. Line: 2px, #D8D0C4. Circle: solid #946070, centered above the line. This echoes the empty-state illustrations in the app. Minimal, distinctive, and legible at tiny sizes because the shape is simple.

**Concept direction 3 — Abstracted 文:**
The character 文 (wen, writing/culture) simplified to its essential strokes — a cross with a descending left-right spread. Rendered as 3px strokes in #946070 on #F2EBE0. At small sizes this reads as an abstract X-like mark. More graphically bold than the other options.

**Recommendation:** Start with concept 1 (漫). It connects directly to the brand name and carries meaning. Test it at 29px, 40px, 60px, and 120px before committing. If it is illegible at 29px, fall back to concept 2.

### App Store Screenshots

**iPhone dimensions:**
- 6.7" display: 1290x2796px (required for App Store)
- 5.5" display: 1242x2208px (required for older device support)

**iPad:** 2048x2732px

**Mac App Store:** 1280x800px

**Screenshot composition:**
- Actual app screen, captured at native resolution
- Device frame: warm-toned (use a cream/linen colored mockup frame, not black or silver — match the brand palette). If no warm frame is available, use no frame at all and add a 2px border in #D8D0C4.
- Caption above the screenshot: Cormorant Garamond, 36pt (iPhone) / 48pt (iPad) / 28pt (Mac), color #2A3650
- Caption background: #F2EBE0, extending 200px (iPhone) / 260px (iPad) / 150px (Mac) above the device frame
- Device frame positioned in the lower 75% of the image, caption in the upper 25%

**Five required screenshots:**

1. **Dashboard** — Caption: "Where you stand, honestly." Shows the mastery bars, stats row, and session history. Demonstrates the diagnostic depth.

2. **Drill session** — Caption: "27 ways to practice what you missed." Shows a drill in progress — ideally a tone pair drill or cloze deletion, something visually distinctive. The large hanzi should be visible.

3. **Graded reader** — Caption: "Read Chinese. Look up what you don't know." Shows a reading passage with the inline gloss popup visible on a tapped word.

4. **Diagnostics** — Caption: "Per-skill HSK readiness. No blended averages." Shows the mastery bars with detailed breakdown — vocabulary, listening, reading, tones tracked independently.

5. **Session complete** — Caption: "Real data after every session." Shows the completion screen with score, accuracy breakdown, and next-session narrative.

### App Store Description

**Apple App Store / Google Play Store — 4,000 character limit:**

```
Mandarin turns your Chinese reading into targeted practice. 27 drill types, honest HSK diagnostics, adaptive scheduling. Free for HSK 1-2.

Read a Chinese passage. Tap a word you don't know. That word enters your drill queue — not as a flashcard, but as practice across tone discrimination, cloze deletion, audio matching, sentence construction, and more. The cleanup loop connects reading to drilling automatically.

HONEST DIAGNOSTICS
Your vocabulary, listening, reading, and tone accuracy are tracked independently. See exactly where each skill stands against HSK benchmarks. No blended averages, no inflated progress bars, no "Great job!" when the data says otherwise.

27 DRILL TYPES
Recognition, production, listening discrimination, tone pairs, cloze comprehension, register awareness, sentence construction, audio-to-character matching. The system picks the right drill type based on your demonstrated performance, not just the skill that's easiest to test.

ADAPTIVE SCHEDULING
Modified FSRS algorithm with bayesian confidence dampening. Review timing, drill type selection, and focus areas all adapt to your actual performance. Zero AI tokens at runtime — everything is deterministic, instant, and works offline.

GRADED READER
Chinese passages matched to your HSK level with inline glosses. Words you look up feed back into your drill queue. Reading and drilling are not separate activities.

HSK PROJECTION
Multi-criteria readiness assessment tells you when you'll be ready for your target HSK level — with confidence intervals, not a single optimistic date.

BUILT FOR ADULTS
No XP. No hearts. No cartoon mascots. No streak-shame notifications. Warm, calm interface designed to feel like a library, not an arcade.

Free: All HSK 1-2 content, no time limit.
Full access: $12/month. 27 drill types, HSK 1-6 content, graded reader, listening practice, speaking drills, full diagnostics.

Built by learners who use the app daily for their own Mandarin study.
```

Character count: ~1,580 (well within the 4,000 limit, leaving room for localized additions).

**First line ("Mandarin turns your Chinese reading...") is critical** — this is what users see before tapping "...more" on both iOS and Android. It must communicate the core value proposition in one sentence.

### Feature Graphic (Google Play)

1024x500px.

- Background: #F2EBE0 (solid, no texture)
- Left side (40% of width): "Mandarin" in Cormorant Garamond 48pt, color #2A3650, left-aligned, vertically centered. Below it: "Every word you look up becomes practice." in Source Serif 4 18pt (Georgia fallback), color #5A6678.
- Right side (60% of width): A single device mockup showing the drill screen with a large Chinese character visible. Device frame in warm tones. Positioned so the device extends slightly below the bottom edge of the graphic (cropped, not floating).
- Horizon line: 1px, #D8D0C4, spanning from left text to right device, vertically centered.
- No other decorative elements.

---

## Presentation / Pitch Deck

### Slide Dimensions

Standard 16:9 (1920x1080px). Export as PDF for sharing, Keynote/Google Slides for presenting.

### Slide Template Specifications

**Title Slide:**
- Background: #F2EBE0
- "Mandarin" in Cormorant Garamond, 72pt, color #2A3650, centered horizontally, positioned at 40% from top
- Horizon line: 1px, #D8D0C4, 48px wide, centered, 24px below the wordmark
- Tagline: "Every word you look up becomes practice." in Source Serif 4, 24pt, color #5A6678, centered, 16px below horizon line
- No subtitle, no date, no "presented by." If context requires attribution, add "Mandarin" in Source Serif 4 14pt, color #8890A0, bottom-center, 40px from bottom edge.

**Content Slide:**
- Background: #F2EBE0
- Heading: Cormorant Garamond, 36pt, color #2A3650, left-aligned. Position: 15% from left edge, 12% from top.
- Body text: Source Serif 4, 20pt, color #5A6678, line-height 1.6. Left-aligned, same 15% left margin.
- Maximum 3 bullet points per slide. If you need more, split across slides. Bullet character: an em dash (--), not a dot. Color #D8D0C4 for the dash, #2A3650 for the text.
- Right margin: 15% from right edge. Top/bottom margins: 12%. This creates generous breathing room.
- No slide numbers. No footer. No logos on content slides.

**Data Slide:**
- Background: #F2EBE0
- Single number: Cormorant Garamond, 120pt, color #946070 (--color-accent), centered horizontally, positioned at 35% from top
- Context label: Source Serif 4, 24pt, color #2A3650, centered, 16px below the number
- Supporting detail (optional): Source Serif 4, 18pt, color #5A6678, centered, 12px below context label
- Never more than one stat per slide. One number, one context line, one optional detail line. Three elements maximum.

**Screenshot Slide:**
- Background: #F2EBE0
- App screenshot centered horizontally, positioned in the upper 70% of the slide
- No device frame (it adds visual noise in a presentation context)
- Drop shadow: 0 2px 8px rgba(42, 54, 80, 0.10) — subtle, just enough to separate the screenshot from the warm background
- Caption: Source Serif 4, 16pt, color #5A6678, centered, 16px below the screenshot
- Screenshot should not exceed 60% of slide width (leave margins for projection)

**Chinese Text Slide:**
- Background: #F2EBE0
- Chinese characters: Noto Serif SC Bold, 96pt, color #946070, centered horizontally, positioned at 30% from top
- Pinyin: Source Serif 4, 24pt, color #5A6678, centered, 16px below characters
- English: Source Serif 4, 20pt, color #8890A0, centered, 12px below pinyin
- Use this slide type for live examples, demonstrations, or to show what a drill looks like as static text. It is the "this is what the learner sees" slide.

**Closing Slide:**
- Background: #F2EBE0
- "Mandarin" in Cormorant Garamond, 48pt, color #2A3650, centered, positioned at 35% from top
- Horizon line: 48px, #D8D0C4, centered, 20px below wordmark
- URL: Source Serif 4, 20pt, color #946070, centered, 24px below horizon
- Email: Source Serif 4, 18pt, color #5A6678, centered, 12px below URL
- "Built by learners. For serious learners." in Source Serif 4, 16pt, color #8890A0, centered, 40px below email

### Color Usage in Presentations

- Background: ALWAYS #F2EBE0 (warm linen). Never white (#FFFFFF). Never dark mode. Never a gradient.
- Text: ALWAYS #2A3650 (--color-text light). Never pure black (#000000).
- Accent: #946070 for highlights, emphasis, and data visualization primary color. Use sparingly — accent means accent.
- Secondary data color: #6A7A5A (--color-secondary, cypress olive). For two-series charts only.
- Never more than 2 colors on a single slide beyond the base palette (background + text + max 2 accent uses).
- Charts: #946070 primary series, #6A7A5A secondary series. No more than 2 data series per chart. Axis labels in Source Serif 4 14pt, #5A6678. Grid lines in #D8D0C4 at 50% opacity.

---

## Print Materials (Minimal)

### Business Card

Standard: 3.5 x 2 inches (89 x 51 mm). Bleed: 0.125 inches per side.

**Front:**
- "Mandarin" in Cormorant Garamond, 18pt, color #2A3650, centered both horizontally and vertically
- Horizon line: 1px, #D8D0C4, 24px wide, centered, 8px below the wordmark
- Nothing else on the front

**Back:**
- mandarinapp.com — Source Serif 4, 11pt, color #2A3650, left-aligned, 24px from left edge, 20px from top
- hello@mandarinapp.com — Source Serif 4, 10pt, color #5A6678, left-aligned, same margin, 6px below URL
- "Patient Mandarin study." — Source Serif 4 Italic, 9pt, color #8890A0, left-aligned, same margin, bottom of card with 20px bottom margin

**Stock and printing:**
- Paper: warm cream, uncoated, 350gsm or heavier. Match the hex #F2EBE0 as closely as possible in paper color. An off-white cotton stock is preferable to bleached white.
- Ink: #2A3650 (coastal indigo) for all text. Single-color print run to reduce cost.
- No accent color (#946070) on the card — bougainvillea rose prints unreliably on uncoated cream stock and can appear as generic pink. The restraint is intentional.
- No embossing, no foil, no spot UV. The card should feel like it was typeset, not manufactured.

### Sticker

3-inch circle (76mm diameter).

**Design:**
- Background: #F2EBE0 (warm linen)
- Center: the character 学 (xue, to study) in Noto Serif SC Bold, 48pt equivalent, color #946070
- Below the character: "Mandarin" in Cormorant Garamond, 10pt, color #5A6678
- Matte laminate finish (not glossy — matches the uncoated aesthetic)

**Alternative sticker option:**
- Same dimensions
- "Mandarin" wordmark in Cormorant Garamond, 14pt, centered, color #2A3650
- Horizon line below: 24px, #D8D0C4
- No Chinese character (for contexts where the character might confuse non-Chinese-reading audiences)

**Use cases:** Laptop stickers, conference swag, included in physical mailings.

---

## Video & Motion

### Video Thumbnail Template

1280x720px (YouTube standard).

**Layout:**
- Background: #F2EBE0 (solid). Never pure white, never black, never a gradient.
- Text: Cormorant Garamond, 48pt, color #2A3650. Left-aligned, positioned in the left 60% of the frame. 3-5 words maximum. If the title needs more words, use a subtitle line in Source Serif 4 24pt, color #5A6678.
- Chinese characters (if relevant to the video topic): Noto Serif SC Bold, 72pt, color #946070. Positioned right of center or upper-right.
- Presenter's face (if appearing in video): occupies the right 30-35% of the frame. Natural expression — neutral or thoughtful. No exaggerated expressions, no pointing, no "surprised face."
- Horizon line: 1px, #D8D0C4, spanning the bottom 40% width of the frame, positioned at the lower third.

**What NOT to include in thumbnails:**
- No arrows, circles, or highlight annotations
- No all-caps text
- No more than 5 words of English text
- No busy backgrounds or collages
- No brand logos other than the app itself (if shown)
- No red or yellow "clickbait" accent colors

### Screen Recording Style

- Browser: clean Chrome or Safari window. Hide bookmarks bar, hide extensions, close other tabs. The URL bar should show only the app URL.
- Resolution: 1920x1080 minimum. 2560x1440 preferred for Retina clarity.
- Cursor: default system cursor. Move naturally — not too fast, not robotically slow. Pause briefly (0.5s) before each click to let viewers see what you are about to interact with.
- Highlight interactions: subtle cursor glow in #946070 at 20% opacity, 24px radius. This can be added in post-production with screen recording software (e.g., ScreenFlow's cursor highlight feature).
- No zooming or panning unless a specific UI element needs magnification. If zooming is necessary, use a slow ease-in/out transition (0.5s), never a snap zoom.
- No background music during narration. Voice should be the only audio.
- If music is needed (montage sections, intro/outro): ambient, warm, no lyrics, no strong rhythm. Reference: Uematsu's quieter pieces (Fisherman's Horizon from FF8, Zanarkand from FF10). Piano, guitar, or strings. Nothing electronic. Volume: -18dB relative to voice narration.

### Intro / Outro Card

Duration: 3-5 seconds each.

**Intro card:**
1. Frame starts as solid #F2EBE0
2. "Mandarin" wordmark fades in with upward drift (translateY 8px to 0, duration 0.5s, ease-out). Cormorant Garamond 48pt, color #2A3650. Centered.
3. 0.5s pause.
4. Tagline fades in below (same animation, 0.3s duration). Source Serif 4 20pt, color #5A6678.
5. Hold for 1.5s, then cut to content.

**Outro card:**
1. Content fades to solid #F2EBE0 (0.3s crossfade)
2. "Mandarin" wordmark appears (same animation as intro, or simply present without animation)
3. URL below: "mandarinapp.com" in Source Serif 4, 18pt, color #946070
4. "Free for HSK 1-2." in Source Serif 4, 16pt, color #8890A0, below the URL
5. Hold for 3s.

**Sound:** No sound effect. If a sound is used, it must be a single warm tone — a soft chime or sustained note at approximately A3 (220Hz), volume -24dB, with a natural decay. No stinger, no whoosh, no percussion.

---

## Content Formatting Standards

### Blog Posts

Blog posts on the Mandarin website or any publishing platform (Substack, Medium, personal site).

**Layout:**
- Max width: 700px, centered
- Margins: auto (centered on page)
- Background: #F2EBE0 or the platform's default (for Medium/Substack, do not fight the platform's native styling)

**Typography:**
- Headings: Cormorant Garamond (on web) or Georgia (on platforms that don't support custom fonts). Sizes: H1 32pt, H2 26pt, H3 22pt. Color #2A3650. No bold on H1/H2 (the size does the work). Bold on H3.
- Body: Source Serif 4 (on web) or Georgia (fallback), 18px, line-height 1.6, color #2A3650. Paragraph spacing: 1.2em between paragraphs.
- Links: color #946070, underlined on hover only. No visited-link color change.

**Chinese examples:**
- Standalone examples: Noto Serif SC, 28px minimum, color #946070, centered on its own line. Pinyin below in Source Serif 4 16pt, color #5A6678. English below that in Source Serif 4 16pt, color #8890A0.
- Inline examples: Noto Serif SC, same size as body text (18px), color #946070. Follow immediately with pinyin in parentheses: 学习 (xuexi).
- Never use sans-serif for Chinese characters in blog posts. Noto Serif SC always.

**Block quotes:**
- Left border: 3px solid #946070 (accent)
- Padding-left: 20px
- Text: Cormorant Garamond Italic, 18px, color #5A6678
- Background: transparent (no shaded box)

**Images:**
- Full width within the 700px content area
- Border-radius: 4px (subtle, just enough to soften)
- No border (the image edge is sufficient)
- Alt text: always provided, descriptive

**Code blocks (if any):**
- Background: #EAE2D6 (--color-surface-alt light)
- Font: Source Code Pro, 15px, color #2A3650
- Padding: 16px
- Border-radius: 0 (matching the app's zero-radius aesthetic)
- No syntax highlighting colors — monochrome only

**No header images.** Blog posts begin with the title and go straight to text. The writing is the content.

### Chinese Character Display Rules

These rules apply across all touchpoints — app, web, social, email, print, presentations.

1. **Font:** Always Noto Serif SC for Chinese characters. Never a sans-serif Chinese font in external-facing materials. (The app uses Noto Sans SC for inline hanzi within body text for optical weight matching with Source Serif 4 — this is an internal exception and does not apply to marketing materials.)

2. **Minimum sizes:**
   - Inline (within English text): 18px
   - Standalone (on its own line, as an example): 24px
   - Featured (hero element, slide centerpiece, social media focus): 48px minimum, 72-120px preferred

3. **Always pair with pinyin.** Chinese characters never appear alone in marketing materials without pinyin. Position: above or below the character, never inline on the same line. Separation: 8px minimum gap.

4. **Tone marks, never tone numbers.** Write ma (first tone) not ma1. Write xue not xue2. The macron/caron/grave/acute marks are required. If the design tool cannot render tone marks, use a Unicode pinyin input method or character map.

5. **Simplified characters by default.** If traditional characters are shown (for Taiwan/Hong Kong context), note it explicitly: "Traditional: 學"

6. **Line height for Chinese text: 2.0 minimum.** Chinese characters need more vertical space than Latin text. The app uses line-height 2.0 for reading passages. Marketing materials should match.

7. **Never letter-space Chinese text.** CSS `letter-spacing` or tracking adjustments break the visual rhythm of Chinese characters. Chinese text should always use `letter-spacing: normal` (0). The built-in spacing in the font is correct.

8. **Color convention:**
   - Featured/highlighted Chinese: #946070 (accent)
   - Chinese within body text: #2A3650 (text color, same as English)
   - Chinese in examples with English translation: #946070 for the characters, #5A6678 for pinyin, #8890A0 for English

---

## Appendix: Do Not

A short list of things that violate the brand, collected here for quick reference.

- Do not use white (#FFFFFF) as a background. Always #F2EBE0.
- Do not use black (#000000) for text. Always #2A3650.
- Do not use sans-serif fonts for headings or body text.
- Do not use rounded corners (border-radius > 0) on any element except subtle image rounding (4px max).
- Do not use gradients except the sky gradient in the app itself.
- Do not add drop shadows heavier than rgba(42, 54, 80, 0.10).
- Do not use exclamation marks in headlines or taglines.
- Do not use emoji in any brand material.
- Do not use stock photography.
- Do not use the words "fun," "easy," "smart," "AI-powered," "revolutionary," or "game-changing."
- Do not create urgency ("Limited time!", "Act now!", "Don't miss out!").
- Do not show dark mode in external marketing (light mode is canonical).
- Do not put more than one CTA in an email.
- Do not put more than one stat on a data slide.
- Do not letter-space Chinese characters.
- Do not use tone numbers instead of tone marks.
- Do not show Chinese characters without pinyin in marketing materials.
