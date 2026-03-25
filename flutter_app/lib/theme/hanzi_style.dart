import 'package:flutter/material.dart';

/// Pre-defined text styles for hanzi display across the app.
///
/// Font family selection: At sizes below 18px, Noto Sans SC is preferred over
/// Noto Serif SC because serif strokes become illegible on low-DPI Android
/// devices. Use [fontFamilyForSize] to resolve the correct family automatically.
class HanziStyle {
  HanziStyle._();

  /// Returns the appropriate CJK font family based on size.
  /// Below 18px, uses sans-serif for legibility on low-DPI screens.
  static String fontFamilyForSize(double fontSize) {
    return fontSize < 18 ? 'NotoSansSC' : 'NotoSerifSC';
  }

  /// Large hanzi for drill display (48px).
  static const display = TextStyle(
    fontFamily: 'NotoSerifSC',
    fontSize: 48,
    fontWeight: FontWeight.w700,
    height: 1.3,
  );

  /// Inline hanzi within body text (14px).
  /// Uses Noto Sans SC — serif strokes are illegible at this size on low-DPI
  /// Android screens.
  static const inline = TextStyle(
    fontFamily: 'NotoSansSC',
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
  /// Uses Noto Sans SC — serif strokes are illegible at this size on low-DPI
  /// Android screens.
  static const compact = TextStyle(
    fontFamily: 'NotoSansSC',
    fontSize: 16,
    fontWeight: FontWeight.w500,
    height: 1.4,
  );
}
