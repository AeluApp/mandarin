# Aelu UX/UI Playbook — Agentic Reference

> This document captures UX/UI best practices, current state, gaps, and improvement
> recipes for the Aelu Mandarin learning app. Any AI agent working on aelu's
> interface should read this first.

## Brand Design Principles

These are inviolable. Every UI change must respect them:

1. **Patient, not gamified.** No points, levels, leaderboards, streaks-as-pressure.
   Consecutive days are noted, not celebrated.
2. **Calm adult voice.** No "Great job!" or "Keep it up!" — factual, forward-directed.
3. **Continuous surface.** Zero border-radius. Horizon-line dividers. Plaster aesthetic.
4. **Motion decelerates into rest.** Things arrive, they don't pop or bounce.
5. **Earth tones.** Warm linen, bougainvillea rose, cypress olive, coastal indigo.
   Correct = sage green. Incorrect = warm brown (never red/alarm).
6. **Information in typography and spacing, not widgets.** Data lives in the text flow.
7. **Honest data.** Every metric defensible. Every number traceable.

Reference: `/BRAND.md` and `:root` design tokens in `/mandarin/web/static/style.css`.

## Current Architecture

| Layer | Technology | Key Files |
|-------|-----------|-----------|
| Backend | Python/Flask | `mandarin/web/__init__.py`, 54 route files |
| Frontend (web) | Vanilla JS + CSS | `mandarin/web/static/app.js` (11K lines), `style.css` (9K lines) |
| Templates | Jinja2 HTML | `mandarin/web/templates/` (index, admin, login, register) |
| Mobile (iOS/Android) | Capacitor 6 wrapping web | `mobile/`, `capacitor-bridge.js` |
| Desktop (macOS) | Tauri 2 wrapping web | `desktop/tauri-app/` |
| Flutter | Scaffold only | `flutter_app/` (not production-ready) |
| Marketing | Static HTML | `marketing/landing/` (31 pages) |

### Design Token Locations

- **App tokens:** `mandarin/web/static/style.css` lines 1-127 (`:root {}`)
- **Dark mode tokens:** same file, `@media (prefers-color-scheme: dark)` and `html[data-theme="dark"]`
- **Marketing tokens:** `marketing/landing/index.html` inline `<style>` (DUPLICATED — should reference app tokens)
- **Admin tokens:** `mandarin/web/templates/admin.html` inline `<style>` (extends app tokens)

## Design System Inventory

### Colors
| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--color-base` | `#F2EBE0` | `#1C2028` | Background |
| `--color-text` | `#2A3650` | `#E4DDD0` | Body text |
| `--color-accent` | `#946070` | `#B07888` | Interactive elements, CTAs |
| `--color-correct` | `#5A7A5A` | `#7A9A7A` | Correct feedback |
| `--color-incorrect` | `#806058` | `#A8988E` | Incorrect feedback (NOT red) |
| `--color-secondary` | `#6A7A5A` | `#8AAA7A` | Supporting elements |
| `--color-divider` | `#D8D0C4` | `#3A3530` | Horizon lines |

### Typography
- Headings: Cormorant Garamond
- Body: Source Serif 4
- Hanzi: Noto Serif SC (display), Noto Sans SC (UI)
- Scale: 1.2 ratio (minor third), `--text-xs` through `--text-display`

### Spacing
- 8px base grid: `--space-1` (0.25rem) through `--space-8` (4rem)

### Motion
- Press: 0.1s, Snappy: 0.15s, Fast: 0.2s, Base: 0.4s, Slow: 0.5s, Ambient: 1.8s
- Easing: `cubic-bezier(0.25, 0.1, 0.25, 1)` — decelerating
- NEVER use bounce/elastic easing

### Touch Targets
- Minimum 44px on all interactive elements (enforced)

### Accessibility Standards
- WCAG AA minimum (4.5:1 small text, 3:1 large text)
- Skip link present (`<a href="#app" class="skip-link">`)
- Focus-visible outlines (2px solid accent, 2px offset)
- ARIA live regions on status bar
- Semantic HTML throughout

## Gaps and Improvement Recipes

Each recipe below is designed to be independently executable by an AI agent.

---

### GAP-01: Mobile Swipe Gestures

**Problem:** On phones, learners can't swipe between drill items. They must tap buttons.
**Impact:** High — swipe is the expected mobile interaction pattern.
**Scope:** `app.js` drill navigation, `style.css` touch handling.

**Recipe:**
1. Add touch event listeners (touchstart/touchmove/touchend) to the drill container
2. Detect horizontal swipe (>50px, <300ms)
3. Swipe left = next drill, swipe right = previous review
4. Add CSS transition for slide-out/slide-in animation (use `--duration-fast`)
5. Ensure haptic feedback fires via `CapacitorBridge.hapticFeedback('light')`
6. Test: works on iOS Safari, Android Chrome, and desktop (no-op)
7. Accessibility: swipe must NOT be the only way to navigate (buttons remain)

**Files:** `mandarin/web/static/app.js`, `mandarin/web/static/style.css`

---

### GAP-02: Pull-to-Refresh on Mobile

**Problem:** No pull-to-refresh gesture on the dashboard.
**Impact:** Medium — users expect it on mobile web/native apps.

**Recipe:**
1. Add touchstart/touchmove/touchend on dashboard section
2. If at scroll top and pulling down >60px, show refresh indicator
3. Use a subtle horizon-line animation (not a spinner — on brand)
4. Trigger dashboard data re-fetch on release
5. Only enable when `window.scrollY === 0`
6. Works via Capacitor and PWA; no-op on desktop

**Files:** `mandarin/web/static/app.js`, `mandarin/web/static/style.css`

---

### GAP-03: Inline Form Validation

**Problem:** Wrong email format or short passwords only show errors after form submission.
**Impact:** Medium — users waste time and get confused.

**Recipe:**
1. Add `input` event listeners on email/password fields in login.html and register.html
2. Validate on blur (not on every keystroke — respects the user)
3. Show validation hint below field using `aria-describedby` linked text
4. Email: check basic format with regex
5. Password: check minimum length (12 chars, per current `minlength` attribute)
6. Confirm password: check match
7. Use `--color-incorrect` for error text, `--color-correct` for valid
8. Never block typing — only show hints after first blur

**Files:** `mandarin/web/templates/login.html`, `mandarin/web/templates/register.html`, `mandarin/web/static/style.css`

---

### GAP-04: Admin Tab Accessibility

**Problem:** Admin tab buttons don't declare `role="tab"` or manage `aria-selected`.
**Impact:** Medium — screen reader users can't navigate admin efficiently.

**Recipe:**
1. Add `role="tablist"` to `.admin-tabs` container
2. Add `role="tab"` + `aria-selected="true|false"` to each `.admin-tab` button
3. Add `role="tabpanel"` + `aria-labelledby` to each `.admin-tab-content`
4. Add `id` to each tab button matching `aria-labelledby` on panel
5. Add arrow key navigation (left/right to switch tabs)
6. Update JS tab-switching to manage aria-selected state

**Files:** `mandarin/web/templates/admin.html`

---

### GAP-05: Admin Cookie Consent Inconsistency

**Problem:** Admin page loads GA4 immediately without checking cookie consent.
Main app correctly gates GA4 behind consent.
**Impact:** Low-medium — legal/compliance gap.

**Recipe:**
1. In admin.html, wrap GA4 loading in the same consent check used in index.html
2. Replace direct `<script async src="gtag...">` with the `_loadGA4()` pattern
3. Check `localStorage.getItem('aelu_cookie_consent') === 'accepted'` before loading

**Files:** `mandarin/web/templates/admin.html`

---

### GAP-06: Marketing Site Conversion Improvements

**Problem:** Marketing site is a clean brochure but doesn't actively sell.
No social proof, no demo, no scroll animations, no urgency.
**Impact:** High — directly affects signups and revenue.

**Recipe (multi-step):**
1. **Scroll-triggered reveals:** Add IntersectionObserver to fade-in sections as user scrolls (use `--duration-base` timing, `--ease-upward` easing)
2. **Social proof section:** Add a "What learners say" section with 3 testimonial cards (placeholder content until real testimonials exist)
3. **Interactive demo:** Embed a mini drill preview (static mockup with CSS animations showing a sample question → answer → feedback cycle)
4. **Stat counters:** Add animated number counters for key metrics ("X words in curriculum", "Y drill types", "Z% retention rate")
5. **Video placeholder:** Add a hero video area (can be a looping CSS animation of the app interface until real video exists)
6. **Sticky CTA:** Add a floating "Start learning" button that appears after scrolling past hero
7. **Dark mode:** Marketing site supports `prefers-color-scheme` but not the time-of-day toggle — add it for consistency

**Files:** `marketing/landing/index.html`, `marketing/landing/*.html`

---

### GAP-07: Shared Design Token File

**Problem:** Marketing site duplicates design token values instead of importing from the app.
Values can drift (and some already have — marketing uses different spacing scale).
**Impact:** Medium — brand consistency risk.

**Recipe:**
1. Extract design tokens from `style.css :root` into a standalone `tokens.css` file
2. `@import` this file in both `style.css` and marketing pages
3. Or: generate a `<link>` to a shared tokens stylesheet served from the app
4. Update marketing inline `<style>` to use `var()` references instead of hardcoded values
5. Verify: compare all hex values and spacing values between marketing and app

**Files:** `mandarin/web/static/style.css`, `marketing/landing/index.html` (and all 31 marketing pages)

---

### GAP-08: Content-Shaped Loading Skeletons

**Problem:** Loading states use generic gray boxes or text placeholders.
**Impact:** Low-medium — perceived performance and polish.

**Recipe:**
1. Create skeleton variants that match the shape of actual content:
   - Dashboard stats row: 4 skeleton cards matching stat dimensions
   - Drill area: skeleton message bubbles with shimmer
   - Panel content: skeleton text lines with varying widths
2. Use CSS `@keyframes shimmer` with a horizontal gradient sweep
3. Shimmer color: `var(--color-surface-alt)` to `var(--color-surface)` — subtle
4. Duration: `--duration-ambient` (1.8s)
5. Add `aria-busy="true"` to containers during loading

**Files:** `mandarin/web/static/style.css`, `mandarin/web/static/app.js`

---

### GAP-09: Tablet-Optimized Layout

**Problem:** Only two layout modes exist (phone and desktop). Tablets get the phone layout.
**Impact:** Medium — iPad/Android tablet users get a cramped experience.

**Recipe:**
1. Add `@media (min-width: 768px) and (max-width: 1024px)` breakpoint
2. Dashboard: side-by-side stats + drill start panel
3. Drill area: wider content area, larger hanzi display
4. Reading: two-column layout (text + vocabulary sidebar)
5. Admin: full table layouts without horizontal scroll
6. Keep touch targets at 44px minimum
7. Test: iPad (1024x768), Android tablet (800x1280)

**Files:** `mandarin/web/static/style.css`

---

### GAP-10: Onboarding Walkthrough

**Problem:** New users land on the dashboard with no guidance. There's an onboarding
checklist but no step-by-step walkthrough.
**Impact:** High — first-time experience determines retention.

**Recipe:**
1. Detect first-ever login (check server-side flag or `localStorage`)
2. Show a 4-step overlay walkthrough:
   - Step 1: "This is your dashboard — it shows what you know" (highlight stats row)
   - Step 2: "Press Begin to start studying" (highlight Begin button)
   - Step 3: "Drills adapt to what you need" (show sample drill)
   - Step 4: "Read, listen, and practice grammar when you're ready" (highlight exposure buttons)
3. Walkthrough uses a semi-transparent overlay with a spotlight on the active element
4. Dismiss with "Got it" button or Escape key
5. Never show again after completion (persist in localStorage + server)
6. Style: use brand colors, Cormorant Garamond headings, no emojis

**Files:** `mandarin/web/static/app.js`, `mandarin/web/static/style.css`, `mandarin/web/templates/index.html`

---

### GAP-11: Marketing Site Responsive Navigation

**Problem:** Marketing site navigation needs verification on small screens.
**Impact:** Medium — mobile visitors can't navigate.

**Recipe:**
1. Add hamburger menu for screens < 768px
2. Menu slides in from right (use `--duration-fast` + `--ease-default`)
3. Close on outside click or Escape
4. Include: Home, Pricing, How it works, FAQ, Login
5. Hamburger icon: three horizontal lines using CSS (no icon library needed)
6. aria-expanded, aria-controls on toggle button

**Files:** `marketing/landing/index.html` (and shared across all marketing pages via nav partial)

---

### GAP-12: Image Responsiveness

**Problem:** Images don't use `srcset` or responsive sizes.
**Impact:** Low — affects load time on slow connections.

**Recipe:**
1. Add `srcset` with 1x/2x variants for illustration PNGs
2. Add `sizes` attribute matching layout breakpoints
3. Use `loading="lazy"` on below-fold images
4. Add `width` and `height` attributes to prevent layout shift (CLS)
5. Generate 2x variants of key illustrations

**Files:** `mandarin/web/templates/index.html`, `marketing/landing/index.html`

---

### GAP-13: Admin Search and Filter

**Problem:** Admin data tables have no search, filter, or pagination.
**Impact:** Medium — as user base grows, admin becomes unusable.

**Recipe:**
1. Add search input above each admin table (filter rows client-side)
2. Add column sort (click header to sort ascending/descending)
3. Add pagination (20 rows per page, with "next/prev" and page numbers)
4. Style search input using existing `--card-padding`, `--color-border` tokens
5. Add `aria-label="Search sessions"` to each search input

**Files:** `mandarin/web/templates/admin.html`

---

## Cross-Platform Checklist

When making any UI change, verify against all platforms:

| Platform | How to test | Key concerns |
|----------|------------|--------------|
| **Web (desktop)** | `flask run` + browser | Hover states, keyboard nav, wide layout |
| **Web (mobile)** | Browser DevTools responsive mode | Touch targets, safe areas, viewport units |
| **iOS (Capacitor)** | `cd mobile && npx cap run ios` | Safe area insets, status bar, haptics, keyboard |
| **Android (Capacitor)** | `cd mobile && npx cap run android` | Back button, keyboard, status bar |
| **macOS (Tauri)** | `cd desktop/tauri-app && cargo tauri dev` | Window resize, menu bar, native feel |
| **PWA** | Chrome > "Install" | Offline, standalone mode, splash screen |

### Safe Area CSS Pattern
```css
padding-top: calc(var(--space-6) + env(safe-area-inset-top, 0px));
padding-bottom: env(safe-area-inset-bottom, 0px);
```

### Keyboard-Visible CSS Pattern
```css
.keyboard-visible #input-area {
  padding-bottom: var(--keyboard-height, 0px);
}
```

### Touch-Only vs Hover
```css
@media (hover: hover) {
  .btn:hover { opacity: 0.88; }
}
```

## Using Open-Source Models for UX Improvements

Aelu already uses Ollama with Qwen for content generation. The same setup can be
used for UX improvement work:

1. **Layout suggestions:** Prompt Qwen/Llama with current HTML structure + brand guide,
   ask for layout alternatives that match the design principles
2. **Copy improvements:** Use local LLM to rewrite marketing copy, error messages,
   empty states to match the "calm adult" voice
3. **Accessibility audit:** Use LLM to scan HTML templates for missing ARIA attributes,
   semantic HTML issues, contrast problems
4. **CSS optimization:** Use LLM to identify duplicate/unused CSS rules in the 9K-line file

### Prompt Template for UX Tasks
```
You are improving the UX of Aelu, a Mandarin learning app.
Brand voice: calm, data-grounded, no praise inflation.
Visual: Mediterranean civic — warm linen, bougainvillea, zero radius, serif fonts.
Motion: decelerates into rest, never bounces.

Current code: [paste relevant section]
Task: [describe improvement]
Constraints: Must work on web, iOS (Capacitor), Android, macOS (Tauri).
```

## Priority Order for Improvements

1. **GAP-10:** Onboarding walkthrough (highest retention impact)
2. **GAP-01:** Mobile swipe gestures (expected mobile UX)
3. **GAP-06:** Marketing conversion (revenue impact)
4. **GAP-03:** Inline form validation (reduces signup friction)
5. **GAP-04:** Admin tab accessibility (compliance)
6. **GAP-05:** Admin cookie consent fix (compliance)
7. **GAP-09:** Tablet layout (growing audience)
8. **GAP-08:** Loading skeletons (perceived performance)
9. **GAP-07:** Shared design tokens (maintainability)
10. **GAP-02:** Pull-to-refresh (mobile polish)
11. **GAP-11:** Marketing responsive nav (mobile visitors)
12. **GAP-13:** Admin search/filter (admin usability)
13. **GAP-12:** Image responsiveness (performance)
