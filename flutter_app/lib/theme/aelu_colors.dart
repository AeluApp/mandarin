import 'package:flutter/material.dart';

/// Civic Sanctuary color tokens — maps 1:1 with CSS custom properties.
class AeluColors {
  AeluColors._();

  // ── Light mode ──
  static const Color baseLight = Color(0xFFF2EBE0);       // --color-base
  static const Color surfaceLight = Color(0xFFF2EBE0);     // --color-surface (same as base)
  static const Color surfaceAltLight = Color(0xFFEDE5D8);  // --color-surface-alt
  static const Color textLight = Color(0xFF2A3650);        // --color-text (slate blue)
  static const Color textDimLight = Color(0xFF5A6478);     // --color-text-dim
  static const Color textFaintLight = Color(0xFF8A8E98);   // --color-text-faint
  static const Color accent = Color(0xFF946070);           // --color-accent (terracotta rose)
  static const Color accentDim = Color(0xFFB48898);        // --color-accent-dim
  static const Color secondary = Color(0xFF6A7A5A);        // --color-secondary (olive)
  static const Color correct = Color(0xFF5A7A5A);          // --color-correct (forest green)

  // ── Dark mode ──
  static const Color baseDark = Color(0xFF1C2028);         // --color-base (dark)
  static const Color surfaceDark = Color(0xFF1C2028);      // --color-surface (dark)
  static const Color surfaceAltDark = Color(0xFF252A34);   // --color-surface-alt (dark)
  static const Color textDark = Color(0xFFE4DDD0);         // --color-text (dark)
  static const Color textDimDark = Color(0xFFB0A898);      // --color-text-dim (dark)
  static const Color textFaintDark = Color(0xFF787068);    // --color-text-faint (dark)

  // ── Dark mode semantic overrides (contrast-safe on #1C2028) ──
  static const Color accentDark = Color(0xFFB8808E);    // terracotta rose — 5.06:1
  static const Color secondaryDark = Color(0xFF8AA070); // olive — 5.71:1
  static const Color incorrectDark = Color(0xFFB08878); // warm brown — 5.28:1
  static const Color correctDark = Color(0xFF7AA07A);   // forest green — 4.95:1

  // ── Semantic aliases ──
  static const Color streakGold = Color(0xFFD4A574);
  static const Color incorrect = Color(0xFF6A4840);       // --color-incorrect (warm brown, 6.79:1 on light)
  static const Color muted = Color(0xFF8A8278);
  static const Color mutedDark = Color(0xFFA89A90);       // 5.98:1 on dark
  static const Color divider = Color(0xFFD4CEC4);
  static const Color dividerDark = Color(0xFF3A3F4A);

  // ── On-accent (text/icons on accent backgrounds) ──
  static const Color onAccent = Color(0xFFFFFFFF);        // white — 4.89:1 on accent

  // ── Accent gradient (for primary CTA) ──
  static const Color accentLight = Color(0xFFA46878);     // lighter center
  static const Color accentDeep = Color(0xFF845060);      // darker edge

  // ── Overlay ──
  static const Color overlay = Color(0xFF1C2028);         // matches baseDark

  // ── Mastery stage colors ──
  static const Color masteryDurable = Color(0xFF4A7A4A);
  static const Color masteryStable = Color(0xFF5A8A5A);
  static const Color masteryStabilizing = Color(0xFF7A9A6A);
  static const Color masteryPassed = Color(0xFF9AAA7A);
  static const Color masterySeen = Color(0xFFBAAA8A);
  static const Color masteryUnseen = Color(0xFFD4CEC4);

  // ── Sky gradient (light) ──
  static const Color skyTopLight = Color(0xFFD8D0C4);
  static const Color skyBottomLight = Color(0xFFF2EBE0);

  // ── Sky gradient (dark) ──
  static const Color skyTopDark = Color(0xFF14181E);
  static const Color skyBottomDark = Color(0xFF1C2028);

  // ── Theme-aware resolvers (contrast-safe in both modes) ──

  static Color accentOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? accentDark : accent;

  static Color secondaryOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? secondaryDark : secondary;

  static Color correctOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? correctDark : correct;

  static Color incorrectOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? incorrectDark : incorrect;

  static Color mutedOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? mutedDark : muted;
}
