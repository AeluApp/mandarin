# ADR-007: "Civic Sanctuary" Design System

## Status

Accepted (2026-01)

## Context

Aelu needed a visual identity and interaction design philosophy for its web and mobile interfaces. Most language learning apps (Duolingo, Babbel, Busuu) use gamified design: bright colors, streak counters, XP points, leaderboards, and celebration animations. This approach drives engagement metrics but creates anxiety, guilt, and extrinsic motivation dependency in adult learners.

Aelu's target user is an adult learner who wants calm, focused study sessions -- not a game.

## Decision Drivers

- Target audience: adult professionals learning Mandarin (not children, not casual gamers)
- Anti-anxiety: streak guilt and gamification anxiety are explicitly unwanted
- Aesthetic coherence: the app's look should reflect its pedagogical philosophy (patient, grounded, respectful)
- Accessibility: must work in light and dark modes, high contrast, screen readers
- Cultural sensitivity: Chinese cultural aesthetics should inform the design without exoticization

## Considered Options

### Option 1: Gamified (Duolingo-style)

Green/purple palette, mascot, XP points, streak flames, celebration animations, sound effects on correct answers.

- **Pros**: Proven engagement driver, familiar to language learners, high short-term retention
- **Cons**: Creates streak anxiety, extrinsic motivation crowds out intrinsic motivation, infantilizing for adult learners, difficult to differentiate from Duolingo

### Option 2: Minimal (Notion-style)

Black/white, sans-serif, lots of whitespace, no decoration.

- **Pros**: Clean, professional, accessible, easy to implement
- **Cons**: Cold, impersonal, no emotional resonance, doesn't feel like a place you'd want to spend time

### Option 3: Civic Sanctuary (chosen)

Warm stone backgrounds, teal and terracotta accents, serif headings (Cormorant Garamond), humanist body text (Source Sans 3), dedicated Chinese font (Noto Serif SC), subtle upward-drift animations, Web Audio API for session start/complete sounds, no streak counters or XP.

- **Pros**: Distinctive, calming, culturally informed, adult-appropriate, emotionally warm without being childish
- **Cons**: Unusual for an app (may confuse users expecting gamification), serif fonts are polarizing, warm palette may feel dated to some users

## Decision

Adopt the "Civic Sanctuary" design system with these specifications:

### Color Tokens (CSS Custom Properties)

```css
/* Light mode (default) */
--color-base: #f5f0eb;        /* warm stone */
--color-surface: #ffffff;      /* card backgrounds */
--color-text: #2c2c2c;         /* near-black */
--color-accent: #2a7f8a;       /* teal */
--color-secondary: #c4715b;    /* terracotta */
--color-correct: #4a8c5c;      /* muted green */
--color-incorrect: #b55a5a;    /* muted red */

/* Dark mode (prefers-color-scheme: dark) */
--color-base: #1a1a1a;
--color-surface: #2a2a2a;
--color-text: #e8e0d8;
--color-accent: #5ab8c4;
--color-secondary: #d4886e;
```

### Typography

```css
--font-heading: 'Cormorant Garamond', serif;
--font-body: 'Source Sans 3', sans-serif;
--font-hanzi: 'Noto Serif SC', serif;
```

Hanzi are rendered in `bright_cyan` in CLI mode and with `--font-hanzi` in web mode, ensuring they stand out from surrounding text.

### Motion

- Upward-drift animation on page transitions (subtle, 200ms, ease-out)
- No bouncing, shaking, or celebration explosions
- Correct answers: quiet fade to green, no sound by default
- Session complete: gentle chime via Web Audio API (optional, respects user preference)

### Anti-Patterns (explicitly prohibited)

- No streak flame or streak counter
- No XP points or level-up screens
- No leaderboards
- No "you missed a day!" guilt messaging
- No mascot
- No confetti or celebration animations

The momentum indicator shows engagement without anxiety: a quiet upward-drift visual that reflects consistency without counting or shaming.

## Consequences

### Positive

- **Distinctive brand**: No other language learning app looks like Aelu. The warm, institutional aesthetic (influences: Fisherman's Horizon, Zeniba's cottage, municipal libraries) creates immediate recognition.
- **Anti-anxiety**: Users report feeling calm during sessions rather than pressured. The absence of streak counters removes the most common source of language app guilt.
- **Dark mode native**: CSS custom properties make dark mode a simple media query swap. The warm dark palette (stone tones, not pure black) maintains the Civic Sanctuary feel.
- **Cross-platform consistency**: CSS variables in inline styles (via `bridge.py`) ensure the same aesthetic in web, iOS (Capacitor), and macOS.
- **Accessibility**: High contrast ratios (teal on stone passes WCAG AA), serif fonts aid readability for extended study sessions, Web Audio API sounds respect system mute.

### Negative

- **Gamification seekers**: Users who expect Duolingo-style rewards may find Aelu boring or unmotivating. This is an intentional tradeoff, not a bug.
- **Serif polarization**: Cormorant Garamond is beautiful but some users find serif fonts old-fashioned. Source Sans 3 for body text balances this.
- **Development cost**: Custom design system requires more CSS than using a framework like Tailwind or Bootstrap. Every component is hand-styled.
- **Marketing challenge**: Screenshots of a calm, serif-heavy app are harder to make exciting in App Store listings than screenshots of a gamified app with bright colors and animations.

### Aesthetic Influences

- **Fisherman's Horizon** (Final Fantasy VIII): A peaceful town built on a bridge, self-governing, pacifist. The warm industrial-civic aesthetic.
- **Zeniba's cottage** (Spirited Away): A quiet place of honest work. No spectacle, just craft.
- **Uematsu's piano collections**: The emotional register of simple melodies played honestly.
- **Your Name** (Shinkai): The quality of light -- warm, golden, slightly melancholy.
- **Moombas** (FFVIII): Joyful without being manic. Community without competition.
