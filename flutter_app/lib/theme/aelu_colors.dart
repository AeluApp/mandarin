import 'package:flutter/material.dart';

/// Civic Sanctuary color tokens — maps 1:1 with CSS custom properties.
class AeluColors {
  AeluColors._();

  // ── Light mode ──
  static const Color baseLight = Color(0xFFF2EBE0);       // --color-base
  static const Color surfaceLight = Color(0xFFF2EBE0);     // --color-surface (same as base)
  static const Color surfaceAltLight = Color(0xFFEAE2D6);  // --color-surface-alt
  static const Color textLight = Color(0xFF2A3650);        // --color-text (slate blue)
  static const Color textDimLight = Color(0xFF5A6678);     // --color-text-dim
  static const Color textFaintLight = Color(0xFF6A7080);   // --color-text-faint
  static const Color accent = Color(0xFF946070);           // --color-accent (terracotta rose)
  static const Color accentDim = Color(0xFF7A5060);        // --color-accent-dim
  static const Color secondary = Color(0xFF6A7A5A);        // --color-secondary (olive)
  static const Color correct = Color(0xFF5A7A5A);          // --color-correct (forest green)

  // ── Dark mode ──
  static const Color baseDark = Color(0xFF1C2028);         // --color-base (dark)
  static const Color surfaceDark = Color(0xFF1C2028);      // --color-surface (dark)
  static const Color surfaceAltDark = Color(0xFF242A34);   // --color-surface-alt (dark)
  static const Color textDark = Color(0xFFE4DDD0);         // --color-text (dark)
  static const Color textDimDark = Color(0xFFA09888);      // --color-text-dim (dark)
  static const Color textFaintDark = Color(0xFF787068);    // --color-text-faint (dark)

  // ── Dark mode semantic overrides (contrast-safe on #1C2028) ──
  static const Color accentDark = Color(0xFFB07888);    // terracotta rose — tokens #B07888
  static const Color secondaryDark = Color(0xFF8AAA7A); // olive — tokens #8AAA7A
  static const Color incorrectDark = Color(0xFFA8988E); // warm brown — tokens #A8988E
  static const Color correctDark = Color(0xFF7A9A7A);   // forest green — tokens #7A9A7A

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

  // ── Glass tokens (semi-transparent surfaces for BackdropFilter) ──
  // Light: surface at 78% opacity, dense at 88%
  static final Color glassBgLight = surfaceLight.withValues(alpha: 0.78);
  static final Color glassBgDenseLight = surfaceLight.withValues(alpha: 0.88);
  static final Color glassBorderLight = divider.withValues(alpha: 0.40);

  // Dark: surfaceAlt at 72% opacity, dense at 85%
  static final Color glassBgDark = surfaceAltDark.withValues(alpha: 0.72);
  static final Color glassBgDenseDark = surfaceAltDark.withValues(alpha: 0.85);
  static final Color glassBorderDark = dividerDark.withValues(alpha: 0.30);

  // ── Shadow depth colors ──
  // Light mode: slate-blue tinted shadow (matches --color-shadow: rgba(42,54,80,0.04))
  static const Color shadowLight = Color(0x0A2A3650);     // rgba(42,54,80,0.04)
  static const Color shadowMedLight = Color(0x14000000);   // rgba(0,0,0,0.08) for lg+
  static const Color shadowHeavyLight = Color(0x1A000000); // rgba(0,0,0,0.10) for xl
  static const Color shadowDeepLight = Color(0x24000000);  // rgba(0,0,0,0.14) for 2xl

  // Dark mode: deeper blacks for layered depth
  static const Color shadowDark = Color(0x33000000);       // rgba(0,0,0,0.20)
  static const Color shadowMedDark = Color(0x26000000);    // rgba(0,0,0,0.15)
  static const Color shadowHeavyDark = Color(0x40000000);  // rgba(0,0,0,0.25)
  static const Color shadowDeepDark = Color(0x4D000000);   // rgba(0,0,0,0.30)

  // ── Mesh gradient colors (animated background tints) ──
  // Light: subtle accent/secondary washes over base
  static final Color meshAccentLight = accent.withValues(alpha: 0.06);
  static final Color meshSecondaryLight = secondary.withValues(alpha: 0.04);

  // Dark: subtler washes
  static final Color meshAccentDark = accentDark.withValues(alpha: 0.04);
  static final Color meshSecondaryDark = secondaryDark.withValues(alpha: 0.03);

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

  // ── Glass theme-aware resolvers ──

  static Color glassBgOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? glassBgDark : glassBgLight;

  static Color glassBgDenseOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? glassBgDenseDark : glassBgDenseLight;

  static Color glassBorderOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? glassBorderDark : glassBorderLight;

  // ── Mesh gradient theme-aware resolvers ──

  static Color meshAccentOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? meshAccentDark : meshAccentLight;

  static Color meshSecondaryOf(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? meshSecondaryDark : meshSecondaryLight;
}
