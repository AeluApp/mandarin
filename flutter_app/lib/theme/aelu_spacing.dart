import 'package:flutter/painting.dart';

/// Civic Sanctuary spacing tokens — consistent rhythm across all screens.
///
/// Based on a 4px base unit. Maps to CSS --space-{n} custom properties.
/// Full 8-step scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
class AeluSpacing {
  AeluSpacing._();

  // ── Named aliases (backward-compatible) ──
  static const double xs = 4;    // --space-1 (0.25rem)
  static const double sm = 8;    // --space-2 (0.5rem)
  static const double md = 16;   // --space-4 (1rem)
  static const double lg = 24;   // --space-5 (1.5rem)
  static const double xl = 32;   // --space-6 (2rem)
  static const double xxl = 48;  // --space-7 (3rem)

  // ── Full 8-step numeric scale (maps 1:1 with web --space-{n}) ──
  /// 4px — micro gaps, icon padding
  static const double space1 = 4;    // --space-1  0.25rem
  /// 8px — tight gaps, inline spacing
  static const double space2 = 8;    // --space-2  0.5rem
  /// 12px — item gaps, compact padding
  static const double space3 = 12;   // --space-3  0.75rem
  /// 16px — standard padding, card internals
  static const double space4 = 16;   // --space-4  1rem
  /// 24px — section spacing, generous padding
  static const double space5 = 24;   // --space-5  1.5rem
  /// 32px — major section gaps
  static const double space6 = 32;   // --space-6  2rem
  /// 48px — page-level spacing
  static const double space7 = 48;   // --space-7  3rem
  /// 64px — hero spacing, large breakpoints
  static const double space8 = 64;   // --space-8  4rem

  /// Screen edge padding (horizontal).
  static const double screenH = 20;

  /// Vertical gap between major sections.
  static const double sectionGap = 32;

  /// Vertical gap between items within a section.
  static const double itemGap = 12;

  /// Card internal padding (matches --card-padding vertical).
  static const double cardPadding = 16;

  /// Card internal horizontal padding (matches --card-padding horizontal).
  static const double cardPaddingH = 16;

  /// Panel internal padding (matches --panel-padding).
  static const double panelPadding = 16;

  /// Button internal padding (matches --btn-padding).
  static const EdgeInsets buttonPadding =
      EdgeInsets.symmetric(horizontal: 32, vertical: 14);
}
