# Aelu — Agent Guidelines

## Project Overview

Aelu is a Mandarin learning platform built on a "Civic Sanctuary" aesthetic: warm Mediterranean civic architecture rendered in digital form — plaster walls, bougainvillea rose, cypress olive, coastal indigo at dusk. The surface is continuous, motion decelerates into rest, and typography carries the information hierarchy instead of widgets or badges. The voice is a calm adult: data-grounded, no praise inflation, no gamification. Every visual choice must reinforce this identity.

---

## Design System Rules (MUST follow)

### Color Tokens

Use `--color-*` CSS variables from `design-tokens.json`. **Never hardcode hex values.**

| Token | Light | Dark | Purpose |
|---|---|---|---|
| `base` / `surface` | `#F2EBE0` | `#1C2028` | Warm linen / deep indigo ground |
| `surface-alt` | `#EAE2D6` | `#242A34` | Slightly darker surface for layering |
| `text` | `#2A3650` | `#E4DDD0` | Primary body text |
| `text-dim` | `#5A6678` | `#A09888` | Secondary labels |
| `accent` | `#946070` | `#B07888` | Bougainvillea rose — primary action |
| `secondary` | `#6A7A5A` | `#8AAA7A` | Cypress olive — secondary actions |
| `correct` | `#5A7A5A` | `#7A9A7A` | Sage green — earned, not celebrated |
| `incorrect` | `#806058` | `#A8988E` | Warm brown — not red, not alarm |
| `divider` | `#D8D0C4` | `#3A3530` | Horizon lines |
| `border` | `transparent` | `transparent` | No visible borders by default |

Both light and dark palettes must be maintained. Every new color must have a dark-mode counterpart.

### Typography

Serif throughout. **No sans-serif for body text.**

| Role | Stack |
|---|---|
| Headings | `'Cormorant Garamond', 'Noto Serif SC', Georgia, serif` |
| Body | `'Source Serif 4', 'Noto Serif SC', Georgia, serif` |
| Hanzi | `'Noto Serif SC', 'Noto Sans SC', 'PingFang SC', serif` |
| Mono | `'SF Mono', 'Menlo', 'Consolas', monospace` |

Type scale uses a minor-third ratio (1.2) with fluid `clamp()` sizing.

### Motion

Motion decelerates into rest. Things arrive — they do not pop.

- Use `--ease-upward` (`cubic-bezier(0.0, 0.0, 0.2, 1)`) for entries.
- Use `--ease-exit` (`cubic-bezier(0.4, 0.0, 1, 1)`) for departures.
- **Never bounce.** No spring physics, no overshoot (exception: celebration effects only).
- All animations **MUST** have a `prefers-reduced-motion: reduce` fallback that disables or minimizes motion.

### Borders and Radius

- Default radius: `--radius: 0`. Structural elements have sharp corners.
- Cards: `8px` radius.
- Illustrations: `12px` radius.
- Admin badges: may have small radius.
- No other radius exceptions without explicit design approval.

### Surface

Continuous plaster. The page is one surface, not a stack of cards.

- `--color-border: transparent` — no card borders by default.
- Use horizon-line `--color-divider` for visual separation.
- Glass surfaces (`surface-glass`, `surface-glass-dense`) for floating panels and overlays only.

### Core Principle

**"Beauty without decoration."** Every visual element must serve a function. If removing an element changes nothing about the user's understanding or interaction, it should not be there.

---

## Asset Generation Rules

When an agent detects a missing or low-quality illustration, it can generate candidates using Stable Diffusion XL via `mandarin/ai/asset_generator.py`.

### Style Prompt Template

```
watercolor, warm Mediterranean tones, linen texture, muted bougainvillea rose (#946070)
and cypress olive (#6A7A5A) accents, editorial illustration style, no cartoon, no gradient,
hand-crafted feel, Civic Sanctuary aesthetic
```

### Resolutions

| Use case | Size |
|---|---|
| Hero / OG images | 1200 x 630 |
| Empty states | 600 x 400 |
| Email headers | 600px wide |

### Approval Requirements

- Generated images are **ALWAYS** `values_decision` — queue for human approval, never auto-deploy.
- Generated videos are **ALWAYS** `values_decision` — queue for human approval, never auto-deploy.

### Format

Prefer WebP with JPG fallback.

---

## Design Quality Self-Improvement

- The design quality analyzer (`mandarin/intelligence/analyzers_ui.py`) runs regularly.
- **Clear violations** (token mismatches, missing dark mode) are auto-fixed.
- **Uncertain improvements** (warmer colors, different spacing) are A/B tested.
- A/B test winners are auto-rolled out via graduated deployment.
- Reference docs: `docs/design-audit.md`, `docs/visual-qa-checklist.yaml`, `docs/design-patterns.md`.

---

## Key Files

| File | Purpose |
|---|---|
| `BRAND.md` | Brand identity, voice, visual principles |
| `mandarin/web/static/design-tokens.json` | Canonical color, spacing, and typography tokens |
| `mandarin/web/static/style.css` | All web CSS |
| `mandarin/web/static/visual-elevation.js` | Scroll-reveal animation system |
| `mandarin/web/static/scroll-engine.js` | Scroll progress engine |
| `mandarin/web/static/webgl/ink-atmosphere.js` | WebGL background atmosphere |
| `mandarin/web/static/webgl/celebrations.js` | Celebration particle effects |
| `flutter_app/lib/theme/aelu_theme.dart` | Flutter theme (colors, text styles, spacing) |
| `docs/design-audit.md` | Full design audit — token tables, component catalog |
| `docs/design-patterns.md` | Reusable UI patterns with real class names |
| `docs/visual-qa-checklist.yaml` | Visual QA checklist for automated checks |
| `mandarin/ai/asset_generator.py` | Image/video generation with style enforcement |

---

## Known Issues

### Python 3.14 Segfault During/After Tests

C extensions (torch, scipy, sklearn) can segfault during Python 3.14 test runs. This is a CPython/extension compatibility issue, NOT a test failure. The `tests/conftest.py` has a workaround (`os._exit()` in `pytest_sessionfinish`), and `scripts/run_tests.sh` filters the noise.

**How to run tests without segfault noise:**
```bash
./scripts/run_tests.sh                     # unit tests (default)
./scripts/run_tests.sh tests/e2e/          # e2e tests
./scripts/run_tests.sh tests/ -k "auth"    # filtered
```

**If the segfault kills the process before results print**, run in smaller batches:
```bash
pytest tests/test_foo.py tests/test_bar.py -x -q
```

**Evaluating results**: The segfault does NOT affect test outcomes. If you see `N passed` before the segfault, all N tests truly passed. If the segfault kills the process before printing results, re-run — the crash is non-deterministic and usually resolves on retry.

**Long-term fix**: Upgrade torch, scipy, sklearn to versions with Python 3.14 support when available. Track at: https://github.com/pytorch/pytorch/issues (Python 3.14 compat).

### Scheduled Task Self-Healing

The daily scheduled task (`aelu-self-healing`) is designed to diagnose and fix its own failures from previous runs. If a session terminates early, times out, or segfaults, the next run's Step 0 checks for previous failures and fixes them. Do not worry about individual session failures — the system self-corrects.

---

## What NOT to Do

- **No sans-serif fonts** in body text.
- **No bouncing/spring animations** (except celebration effects).
- **No rounded corners** on structural elements (cards and illustrations are the only exceptions).
- **No gradient text.**
- **No custom cursors.**
- **No praise inflation** ("Amazing!", "Incredible!", "Great job!").
- **No decoration without function** — if removing it changes nothing, remove it.
- **No hardcoded hex colors** — always use `--color-*` tokens.
- **No card borders** — surfaces are continuous plaster.
- **No gamification** — no points, levels, streaks-as-celebration, or leaderboards.
- **NEVER lower coverage floors** in `scripts/coverage_floors.py`. If a floor is not met, write tests to increase coverage — do not reduce the threshold. Coverage floors are a ratchet: they only go up.
- **NEVER lower `--cov-fail-under`** in CI workflows or `fail_under` in `pyproject.toml`. Write tests instead.
