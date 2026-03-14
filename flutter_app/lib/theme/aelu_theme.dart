import 'package:flutter/material.dart';
import 'aelu_colors.dart';

/// Civic Sanctuary theme — warm stone, olive, terracotta.
///
/// Typography: Cormorant Garamond headings, Source Serif 4 body, Noto Serif SC hanzi.
/// Motion: upward-drift (slide + fade from below).
/// Radius: 12px on interactive elements, 0px on structural/decorative.
class AeluTheme {
  AeluTheme._();

  static const _interactiveRadius = BorderRadius.all(Radius.circular(12));
  static const _chipRadius = BorderRadius.all(Radius.circular(8));
  static const _dialogRadius = BorderRadius.all(Radius.circular(16));

  // ── Typography ──

  static TextTheme _textTheme(Color textColor, Color dimColor) {
    return TextTheme(
      displayLarge: TextStyle(
        fontFamily: 'CormorantGaramond',
        fontSize: 32,
        fontWeight: FontWeight.w600,
        color: textColor,
        height: 1.2,
      ),
      displayMedium: TextStyle(
        fontFamily: 'CormorantGaramond',
        fontSize: 28,
        fontWeight: FontWeight.w600,
        color: textColor,
        height: 1.2,
      ),
      headlineLarge: TextStyle(
        fontFamily: 'CormorantGaramond',
        fontSize: 24,
        fontWeight: FontWeight.w600,
        color: textColor,
        height: 1.3,
      ),
      headlineMedium: TextStyle(
        fontFamily: 'CormorantGaramond',
        fontSize: 20,
        fontWeight: FontWeight.w500,
        color: textColor,
        height: 1.3,
      ),
      titleLarge: TextStyle(
        fontFamily: 'SourceSerif4',
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: textColor,
      ),
      titleMedium: TextStyle(
        fontFamily: 'SourceSerif4',
        fontSize: 16,
        fontWeight: FontWeight.w600,
        color: textColor,
      ),
      bodyLarge: TextStyle(
        fontFamily: 'SourceSerif4',
        fontSize: 16,
        fontWeight: FontWeight.w400,
        color: textColor,
        height: 1.5,
      ),
      bodyMedium: TextStyle(
        fontFamily: 'SourceSerif4',
        fontSize: 14,
        fontWeight: FontWeight.w400,
        color: textColor,
        height: 1.5,
      ),
      bodySmall: TextStyle(
        fontFamily: 'SourceSerif4',
        fontSize: 12,
        fontWeight: FontWeight.w400,
        color: dimColor,
        height: 1.4,
      ),
      labelLarge: TextStyle(
        fontFamily: 'SourceSerif4',
        fontSize: 14,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.5,
        color: textColor,
      ),
    );
  }

  // ── Light Theme ──

  static ThemeData light() {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      visualDensity: VisualDensity.standard,
      scaffoldBackgroundColor: AeluColors.baseLight,
      colorScheme: const ColorScheme.light(
        primary: AeluColors.accent,
        secondary: AeluColors.secondary,
        surface: AeluColors.surfaceLight,
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onSurface: AeluColors.textLight,
        error: AeluColors.incorrect,
      ),
      textTheme: _textTheme(AeluColors.textLight, AeluColors.textDimLight),
      appBarTheme: const AppBarTheme(
        backgroundColor: AeluColors.baseLight,
        foregroundColor: AeluColors.textLight,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
          fontFamily: 'CormorantGaramond',
          fontSize: 22,
          fontWeight: FontWeight.w600,
          color: AeluColors.textLight,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AeluColors.accent,
          foregroundColor: Colors.white,
          elevation: 2,
          shadowColor: AeluColors.accent.withValues(alpha: 0.3),
          minimumSize: const Size(44, 44),
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
          textStyle: const TextStyle(
            fontFamily: 'SourceSerif4',
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AeluColors.accent,
          side: const BorderSide(color: AeluColors.accent),
          minimumSize: const Size(44, 44),
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AeluColors.accent,
          minimumSize: const Size(44, 44),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: AeluColors.surfaceAltLight,
        border: OutlineInputBorder(
          borderRadius: _interactiveRadius,
          borderSide: BorderSide(color: AeluColors.divider),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: _interactiveRadius,
          borderSide: BorderSide(color: AeluColors.divider),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: _interactiveRadius,
          borderSide: BorderSide(color: AeluColors.accent, width: 2.5),
        ),
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      cardTheme: const CardThemeData(
        color: AeluColors.surfaceLight,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: _interactiveRadius,
          side: BorderSide(color: AeluColors.divider, width: 0.5),
        ),
        margin: EdgeInsets.symmetric(vertical: 8),
      ),
      chipTheme: const ChipThemeData(
        shape: RoundedRectangleBorder(borderRadius: _chipRadius),
      ),
      dialogTheme: const DialogThemeData(
        shape: RoundedRectangleBorder(borderRadius: _dialogRadius),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: AeluColors.divider,
        thickness: 0.5,
      ),
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.android: FadeUpwardsPageTransitionsBuilder(),
        },
      ),
    );
  }

  // ── Dark Theme ──

  static ThemeData dark() {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      visualDensity: VisualDensity.standard,
      scaffoldBackgroundColor: AeluColors.baseDark,
      colorScheme: const ColorScheme.dark(
        primary: AeluColors.accentDark,
        secondary: AeluColors.secondaryDark,
        surface: AeluColors.surfaceDark,
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onSurface: AeluColors.textDark,
        error: AeluColors.incorrectDark,
      ),
      textTheme: _textTheme(AeluColors.textDark, AeluColors.textDimDark),
      appBarTheme: const AppBarTheme(
        backgroundColor: AeluColors.baseDark,
        foregroundColor: AeluColors.textDark,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
          fontFamily: 'CormorantGaramond',
          fontSize: 22,
          fontWeight: FontWeight.w600,
          color: AeluColors.textDark,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AeluColors.accentDark,
          foregroundColor: Colors.white,
          elevation: 2,
          shadowColor: AeluColors.accentDark.withValues(alpha: 0.3),
          minimumSize: const Size(44, 44),
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
          textStyle: const TextStyle(
            fontFamily: 'SourceSerif4',
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AeluColors.accentDark,
          side: const BorderSide(color: AeluColors.accentDark),
          minimumSize: const Size(44, 44),
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AeluColors.accentDark,
          minimumSize: const Size(44, 44),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: AeluColors.surfaceAltDark,
        border: OutlineInputBorder(
          borderRadius: _interactiveRadius,
          borderSide: BorderSide(color: AeluColors.dividerDark),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: _interactiveRadius,
          borderSide: BorderSide(color: AeluColors.dividerDark),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: _interactiveRadius,
          borderSide: BorderSide(color: AeluColors.accentDark, width: 2.5),
        ),
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      cardTheme: const CardThemeData(
        color: AeluColors.surfaceDark,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: _interactiveRadius,
          side: BorderSide(color: AeluColors.dividerDark, width: 0.5),
        ),
        margin: EdgeInsets.symmetric(vertical: 8),
      ),
      chipTheme: const ChipThemeData(
        shape: RoundedRectangleBorder(borderRadius: _chipRadius),
      ),
      dialogTheme: const DialogThemeData(
        shape: RoundedRectangleBorder(borderRadius: _dialogRadius),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: AeluColors.dividerDark,
        thickness: 0.5,
      ),
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.android: FadeUpwardsPageTransitionsBuilder(),
        },
      ),
    );
  }
}
