# UX Polish Notes (2026-02-24)

## 1. "IME" Jargon Replaced with "Typing"

**What was wrong:** User-facing labels, charts, and diagnostics used "IME" (Input Method Editor), which is meaningless to learners.

**Root cause:** Internal engineering term leaked into UI text.

**Fix:** Replaced all user-facing "IME" with "Typing" across 7 files. Created `mandarin/ui_labels.py` as a canonical glossary mapping internal identifiers to user-facing labels. Wired `dispatch.py` and `scheduler.py` to pull labels from this glossary.

**Files:** `dispatch.py`, `scheduler.py`, `cli.py`, `diagnostics.py`, `improve.py`, `app.js`, `ui_labels.py` (new)

**How verified:** Grep for user-facing "IME" returns zero hits. Internal identifiers (`ime_type`, `ime_confusable`, `"ime"` modality key) unchanged.

**Additional fixes (round 2):**
- Dashboard forecast panel: modality key "ime" was rendered as "Ime" via naive capitalization. Added label mapping dict in `app.js` to display "Typing" instead.
- Dashboard error patterns: internal `error_type` values (e.g. `ime_confusable`) rendered raw in Jinja2 template. Added `error_labels` dict in `index.html` to map all 14 error types to user-friendly names (e.g. "Typing confusable", "Phonetics", "Register").

---

## 2. Session Accounting Tightened

**What was wrong:** `total_sessions` incremented on every `end_session()` call, including abandoned and bounced sessions. Streaks counted any day with `items_completed > 0`, inflating progress.

**Root cause:** No distinction between completed and abandoned sessions when updating profile counters and computing streaks.

**Fix:**
- `end_session()` only increments `total_sessions` when `outcome == "completed"`
- Streak query adds `AND session_outcome = 'completed'`
- Session history API now includes `session_outcome` field
- UI shows "Ended early" badge on abandoned sessions
- Early exit completion message changed to "Session ended early. Drill progress saved."

**Files:** `db/session.py`, `web/routes.py`, `web/static/app.js`, `web/static/style.css`

**How verified:** Abandon a session -> confirm "Sessions" count unchanged, streak unchanged, "Ended early" badge shown in history.

---

## 3. Illustration Rendering Fixed

**What was wrong:** CSS mask-image illustrations may have been invisible due to low contrast (`--color-illustration` was `--color-divider`, nearly identical to `--color-base`) and potential external SVG loading issues in WKWebView.

**Root cause:** (A) Color token mapped to divider color with no opacity control. (B) External SVG file URLs may fail to load as mask-image sources in some browsers.

**Fix:**
- Changed `--color-illustration` from `var(--color-divider)` to `var(--color-accent)` in all 4 theme declarations
- Added `opacity: 0.25` to a shared illustration `::before` base rule (subtle but clearly visible)
- Tripled stroke-widths in existing SVGs (0.5→1.5, 0.75→2.25) and doubled circle radii for mask visibility
- Added filled shapes (rects, circles) in SVGs so the mask has actual area, not just thin strokes
- Added 9 new illustration classes (welcome, gateway, memory, forecast, error, arrival, reading, media, listening) with bold, purpose-designed SVGs
- Updated dark mode selectors to include all new illustration classes

**Files:** `web/static/style.css`

**How verified:** Illustrations now render as teal-tinted shapes at 25% opacity on both light and dark backgrounds. Filled shapes (lanterns, sun, screen, crane body) create clearly visible decorative elements.

---

## 4. About/FAQ List Styling Fixed

**What was wrong:** About page used checkmark characters (`\2713`) that could look like interactive checkboxes. FAQ page used hidden `<input type="checkbox">` elements that could appear as raw checkboxes if CSS fails.

**Root cause:** Decorative pseudo-elements used characters that suggest interactivity. CSS-only accordion relied solely on `display: none` to hide checkbox inputs.

**Fix:**
- About page: replaced checkmark `::before` with a small accent-colored dot (6px circle, 50% opacity)
- FAQ page: added `position: absolute; opacity: 0; pointer-events: none` to `.faq-toggle` for extra robustness
- FAQ page: added `<noscript>` fallback that expands all answers if CSS fails

**Files:** `marketing/landing/about.html`, `marketing/landing/faq.html`

**How verified:** About page shows clean dot bullets. FAQ accordion functions normally; hidden checkbox inputs are triply hidden.

---

## 5. Icon — Transparent Corners

**What was wrong:** Dock icon had opaque linen corners instead of transparent ones, appearing as a square on dark backgrounds.

**Root cause:** `gen_icon.py` filled the entire square with linen (`CGContextFillRect`) before drawing the rounded rect on top with the same color. macOS expects transparent corners (the OS applies its own squircle mask).

**Fix:**
- Removed the full-square `CGContextFillRect` call
- Added `CGContextSaveGState`/`CGContextClip`/`CGContextRestoreGState` to clip text drawing to the rounded rect path
- Regenerated all icon sizes and `.icns`
- Copied output to `desktop/tauri-app/src-tauri/icons/`

**Files:** `MandarinApp/gen_icon.py`, `desktop/tauri-app/src-tauri/icons/*`

**How verified:** Generated PNGs have transparent corners (checkerboard in Preview). Icon renders correctly on both light and dark desktop backgrounds.

---

## 6. Aborted Sessions — Interrupted State

**What was wrong:** Sessions killed by crash or force-quit were left with `session_outcome = 'started'` and no `ended_at`. No cleanup on restart.

**Root cause:** No startup recovery for orphaned sessions.

**Fix:**
- Added startup cleanup in `create_app()` — marks sessions with `session_outcome = 'started'` and `ended_at IS NULL` older than 1 hour as `'interrupted'`
- Added `SESSION_OUTCOME_LABELS` to `ui_labels.py` (completed, abandoned, bounced, interrupted)
- Added `interrupted` badge display in `app.js` session history
- Updated `get_session_funnel()` in `db/session.py` to include `interrupted` count
- `total_sessions` still only counts `completed` (unchanged)

**Files:** `mandarin/web/__init__.py`, `mandarin/ui_labels.py`, `mandarin/db/session.py`, `mandarin/web/static/app.js`

**How verified:** 5 unit tests (`test_session_cleanup.py`): orphaned session cleanup, recent session protection, completed session unaffected, total_sessions excludes interrupted, funnel includes interrupted count.

---

## 7. FAQ/About — Checkbox Fallback & ARIA

**What was wrong:** FAQ checkboxes could become visible if CSS failed to load (CSP blocking).

**Root cause:** Hiding relied solely on CSS `display: none` rule.

**Fix:**
- Added fallback inline `style="display:none"` on every `<input type="checkbox" class="faq-toggle">`
- Added `<script>` to toggle `aria-expanded` attribute on labels when checkboxes change
- FAQ labels already had `role="button"` and `aria-expanded="false"` from earlier work

**Files:** `marketing/landing/faq.html`

**How verified:** FAQ checkboxes invisible even with CSS disabled. ARIA attributes toggle correctly on expand/collapse.

---

## 8. Illustrations — Asset Pipeline

**What was wrong:** 18 SVG files in `marketing/assets/illustrations/` were not served or referenced by any page.

**Root cause:** No Flask route to serve illustration files. No `<img>` tags referencing them.

**Fix:**
- Added `/illustrations/<filename>` route in `landing_routes.py` with path validation
- Added decorative SVG illustrations between About page sections (reading-lamp, stone-bridge, mountain-path)
- Added hero illustration to FAQ page (paper-crane)
- Added `.section-illustration` CSS with low opacity (0.35 light / 0.3 dark), dark mode filter adaptation
- All `<img>` tags have `onerror="this.style.display='none'"` for graceful degradation

**Files:** `mandarin/web/landing_routes.py`, `marketing/landing/about.html`, `marketing/landing/faq.html`

**How verified:** About page shows decorative SVGs between sections. FAQ has hero illustration. Dark mode applies invert filter. Broken image paths hidden gracefully.

---

## 9. Layout Shifted Left

**What was wrong:** Content appeared shifted left in the Tauri window (WKWebView).

**Root cause:** `body` lacked explicit `width: 100%`, and scrollbar appearance/disappearance caused layout shift. `#app` relied solely on flex centering without `margin: 0 auto` fallback.

**Fix:**
- Added `scrollbar-gutter: stable` to `html` — reserves scrollbar space, prevents shift when overflow changes
- Added `width: 100%` to `body`
- Added `margin: 0 auto` to `#app` as backup centering alongside flex

**Files:** `mandarin/web/static/style.css`

**How verified:** `#app` bounding rect is horizontally centered in the viewport (equal left/right margins).

---

## 10. Clickability Bug — Buttons Not Clickable Until Scroll

**What was wrong:** Dashboard buttons sometimes unresponsive until user scrolled, in the Tauri macOS app.

**Root cause:** WKWebView hit-testing stale geometry after splash→app navigation. The splash page remained in bfcache, and WebKit calculated hit-test coordinates against stale layout.

**Fix:**
- Changed `window.location.href = APP_URL` to `window.location.replace(APP_URL)` in splash page — prevents bfcache retention
- Added double-`requestAnimationFrame` compositing nudge in `app.js` DOMContentLoaded — forces WebKit to re-composite the layer tree and recalculate hit-test geometry

**Files:** `desktop/tauri-app/src/index.html`, `mandarin/web/static/app.js`

**How verified:** All dashboard buttons clickable immediately on launch across multiple consecutive launches.

---

## 11. Autosave + Resume

**What was wrong:** Sessions lost on app crash/close. No way to resume after restart.

**Root cause:** WebSocket resume tokens lived in `sessionStorage` and were lost on app restart. Drill progress was saved to SQLite but not surfaced to the user.

**Fix:**

**Client side (`app.js`):**
- Added `SessionCheckpoint` module using `localStorage` with 24h expiry
- Saves session_id, drill_index, drill_total, correct, completed, session_type after each drill
- Cleared on session complete, error, or fresh session start
- On DOMContentLoaded, checks for checkpoint → fetches `/api/session/checkpoint/<id>` → shows resume banner if resumable
- Resume banner: "You have an unfinished session (X/Y drills). [Resume] [Start fresh]"

**Server side:**
- Added `send_progress()` to `bridge.py` — emits progress message after each drill
- Added `progress_fn` parameter to `run_session()` in `runner.py`
- Wired `progress_fn` callback in `routes.py` session handler
- Added `GET /api/session/checkpoint/<session_id>` — validates session is resumable (not completed/bounced/interrupted, has remaining drills, has plan_snapshot)

**CSS:**
- Added `.resume-banner` styling matching Civic Sanctuary aesthetic

**Files:** `mandarin/web/static/app.js`, `mandarin/web/bridge.py`, `mandarin/runner.py`, `mandarin/web/routes.py`, `mandarin/web/static/style.css`

**How verified:** Start session → complete drills → close app → reopen → resume banner appears. "Start fresh" clears checkpoint. 24h-old checkpoints auto-expire. Corrupted JSON gracefully ignored.

---

## QA Checklist

```
[ ] Icon: transparent corners in Dock (light + dark desktop)
[ ] Sessions: orphaned session marked 'interrupted' on restart
[ ] Sessions: total_sessions only counts completed
[ ] FAQ: no visible checkboxes, expand/collapse works
[ ] About: illustrations render between sections
[ ] About: dark mode illustrations adapt
[ ] CSS illustrations: visible on dashboard at 0.5 opacity
[ ] Layout: #app centered in window (equal left/right margins)
[ ] Buttons: all dashboard buttons clickable immediately on launch (10 trials)
[ ] Resume: banner appears after incomplete session + app restart
[ ] Resume: clicking Resume continues from correct drill
[ ] Resume: clicking Start fresh starts new session
[ ] Resume: 24h expiry works
[ ] python -m pytest tests/ -x passes (754 tests)
```
