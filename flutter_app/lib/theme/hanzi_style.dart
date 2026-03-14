import 'package:flutter/material.dart';

/// Pre-defined text styles for hanzi display across the app.
class HanziStyle {
  HanziStyle._();

  /// Large hanzi for drill display (48px).
  static const display = TextStyle(
    fontFamily: 'NotoSerifSC',
    fontSize: 48,
    fontWeight: FontWeight.w700,
    height: 1.3,
  );

  /// Inline hanzi within body text (14px).
  static const inline = TextStyle(
    fontFamily: 'NotoSerifSC',
    fontSize: 14,
    fontWeight: FontWeight.w400,
    height: 1.4,
  );

  /// Reader hanzi for graded reading (22px, generous line height).
  static const reader = TextStyle(
    fontFamily: 'NotoSerifSC',
    fontSize: 22,
    fontWeight: FontWeight.w400,
    height: 1.8,
  );

  /// Compact hanzi for grids and lists (16px).
  static const compact = TextStyle(
    fontFamily: 'NotoSerifSC',
    fontSize: 16,
    fontWeight: FontWeight.w500,
    height: 1.4,
  );
}
