import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'aelu_colors.dart';

/// Civic Sanctuary theme — warm stone, olive, terracotta.
///
/// Typography: Cormorant Garamond headings, Source Serif 4 body, Noto Serif SC hanzi.
/// Motion: upward-drift (slide + fade from below), spring easing for physical gestures.
/// Radius: 12px on interactive elements, 0px on structural/decorative.
/// Depth: 6-level shadow scale (xs → 2xl) matching the web elevation system.
/// Glass: Semi-transparent surfaces designed for use with [BackdropFilter].
class AeluTheme {
  AeluTheme._();

  static const _interactiveRadius = BorderRadius.all(Radius.circular(12));
  static const _chipRadius = BorderRadius.all(Radius.circular(8));
  static const _dialogRadius = BorderRadius.all(Radius.circular(16));

  // ── Spring easing ──
  // Matches web --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1)
  static const Curve springCurve = Cubic(0.34, 1.56, 0.64, 1);

  // ── Duration tokens (matching web) ──
  static const Duration durationPress = Duration(milliseconds: 100);
  static const Duration durationSnappy = Duration(milliseconds: 150);
  static const Duration durationFast = Duration(milliseconds: 200);
  static const Duration durationNormal = Duration(milliseconds: 300);

  // ── Button press scale ──
  /// Scale factor applied during button press (matches web scale(0.98)).
  static const double pressScale = 0.98;

  // ════════════════════════════════════════════════════════════════
  //  6-level shadow / elevation scale
  //  Maps 1:1 with web --shadow-{xs..2xl} tokens.
  // ════════════════════════════════════════════════════════════════

  /// Light mode shadows — subtle slate-blue tinted.
  static final List<List<BoxShadow>> shadowsLight = [
    // xs — 0 1px 1px
    [BoxShadow(color: AeluColors.shadowLight, blurRadius: 1, offset: const Offset(0, 1))],
    // sm — 0 1px 3px, 0 1px 2px
    [
      BoxShadow(color: AeluColors.shadowLight, blurRadius: 3, offset: const Offset(0, 1)),
      BoxShadow(color: AeluColors.shadowLight, blurRadius: 2, offset: const Offset(0, 1)),
    ],
    // md — 0 2px 6px, 0 1px 3px
    [
      BoxShadow(color: AeluColors.shadowLight, blurRadius: 6, offset: const Offset(0, 2)),
      BoxShadow(color: AeluColors.shadowLight, blurRadius: 3, offset: const Offset(0, 1)),
    ],
    // lg — 0 8px 24px rgba(0,0,0,0.08), 0 2px 8px
    [
      BoxShadow(color: AeluColors.shadowMedLight, blurRadius: 24, offset: const Offset(0, 8)),
      BoxShadow(color: AeluColors.shadowLight, blurRadius: 8, offset: const Offset(0, 2)),
    ],
    // xl — 0 16px 48px rgba(0,0,0,0.10), 0 4px 12px rgba(0,0,0,0.05)
    [
      BoxShadow(color: AeluColors.shadowHeavyLight, blurRadius: 48, offset: const Offset(0, 16)),
      BoxShadow(color: const Color(0x0D000000), blurRadius: 12, offset: const Offset(0, 4)),
    ],
    // 2xl — 0 24px 64px rgba(0,0,0,0.14), 0 8px 24px rgba(0,0,0,0.06)
    [
      BoxShadow(color: AeluColors.shadowDeepLight, blurRadius: 64, offset: const Offset(0, 24)),
      BoxShadow(color: const Color(0x0F000000), blurRadius: 24, offset: const Offset(0, 8)),
    ],
  ];

  /// Dark mode shadows — deeper blacks for layered depth.
  static final List<List<BoxShadow>> shadowsDark = [
    // xs
    [BoxShadow(color: AeluColors.shadowDark, blurRadius: 1, offset: const Offset(0, 1))],
    // sm
    [
      BoxShadow(color: AeluColors.shadowDark, blurRadius: 3, offset: const Offset(0, 1)),
      BoxShadow(color: AeluColors.shadowMedDark, blurRadius: 2, offset: const Offset(0, 1)),
    ],
    // md
    [
      BoxShadow(color: AeluColors.shadowDark, blurRadius: 6, offset: const Offset(0, 2)),
      BoxShadow(color: AeluColors.shadowMedDark, blurRadius: 3, offset: const Offset(0, 1)),
    ],
    // lg
    [
      BoxShadow(color: AeluColors.shadowDark, blurRadius: 24, offset: const Offset(0, 8)),
      BoxShadow(color: const Color(0x1F000000), blurRadius: 8, offset: const Offset(0, 2)),
    ],
    // xl
    [
      BoxShadow(color: AeluColors.shadowHeavyDark, blurRadius: 48, offset: const Offset(0, 16)),
      BoxShadow(color: AeluColors.shadowMedDark, blurRadius: 12, offset: const Offset(0, 4)),
    ],
    // 2xl
    [
      BoxShadow(color: AeluColors.shadowDeepDark, blurRadius: 64, offset: const Offset(0, 24)),
      BoxShadow(color: const Color(0x2E000000), blurRadius: 24, offset: const Offset(0, 8)),
    ],
  ];

  /// Named shadow indices for readability.
  static const int shadowXs = 0;
  static const int shadowSm = 1;
  static const int shadowMd = 2;
  static const int shadowLg = 3;
  static const int shadowXl = 4;
  static const int shadow2xl = 5;

  /// Resolve shadow list for current brightness.
  static List<BoxShadow> shadowOf(BuildContext context, int level) {
    assert(level >= 0 && level <= 5, 'Shadow level must be 0–5 (xs–2xl)');
    return Theme.of(context).brightness == Brightness.dark
        ? shadowsDark[level]
        : shadowsLight[level];
  }

  // ════════════════════════════════════════════════════════════════
  //  Glass surface helpers (for use with BackdropFilter)
  // ════════════════════════════════════════════════════════════════

  /// Standard glass blur — blur(20px). Pair with a semi-transparent
  /// surface color from [AeluColors] to approximate CSS
  /// `backdrop-filter: blur(20px) saturate(1.2)`.
  static ImageFilter get glassBlur =>
      ImageFilter.blur(sigmaX: 20, sigmaY: 20, tileMode: TileMode.clamp);

  /// Lighter glass blur for compact elements — blur(12px).
  static ImageFilter get glassBlurLight =>
      ImageFilter.blur(sigmaX: 12, sigmaY: 12, tileMode: TileMode.clamp);

  /// Build a glass-style [BoxDecoration] for the current theme.
  ///
  /// Use inside a [Container] layered beneath a [BackdropFilter].
  /// Set [dense] to true for overlays (88% / 85% opacity).
  /// Optional [shadowLevel] from 0 (xs) to 5 (2xl).
  static BoxDecoration glassDecoration(
    BuildContext context, {
    bool dense = false,
    int? shadowLevel,
    BorderRadius borderRadius = _interactiveRadius,
  }) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return BoxDecoration(
      color: dense
          ? (isDark ? AeluColors.glassBgDenseDark : AeluColors.glassBgDenseLight)
          : (isDark ? AeluColors.glassBgDark : AeluColors.glassBgLight),
      borderRadius: borderRadius,
      border: Border.all(
        color: isDark ? AeluColors.glassBorderDark : AeluColors.glassBorderLight,
        width: 0.5,
      ),
      boxShadow: shadowLevel != null ? shadowOf(context, shadowLevel) : null,
    );
  }

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
          // Press feedback: scale(0.98) via splashFactory + animation duration
          splashFactory: InkSparkle.splashFactory,
          animationDuration: durationPress,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AeluColors.accent,
          side: const BorderSide(color: AeluColors.accent),
          minimumSize: const Size(44, 44),
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
          splashFactory: InkSparkle.splashFactory,
          animationDuration: durationPress,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AeluColors.accent,
          minimumSize: const Size(44, 44),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
          splashFactory: InkSparkle.splashFactory,
          animationDuration: durationPress,
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
      // Glass-style card: semi-transparent background with subtle border.
      // Pair with BackdropFilter for the full frosted effect.
      cardTheme: CardThemeData(
        color: AeluColors.glassBgLight,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: _interactiveRadius,
          side: BorderSide(color: AeluColors.glassBorderLight, width: 0.5),
        ),
        margin: const EdgeInsets.symmetric(vertical: 8),
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
      // Spring-based page transitions.
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.android: _SpringPageTransitionsBuilder(),
          TargetPlatform.macOS: _SpringPageTransitionsBuilder(),
          TargetPlatform.windows: _SpringPageTransitionsBuilder(),
          TargetPlatform.linux: _SpringPageTransitionsBuilder(),
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
          splashFactory: InkSparkle.splashFactory,
          animationDuration: durationPress,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AeluColors.accentDark,
          side: const BorderSide(color: AeluColors.accentDark),
          minimumSize: const Size(44, 44),
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
          splashFactory: InkSparkle.splashFactory,
          animationDuration: durationPress,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AeluColors.accentDark,
          minimumSize: const Size(44, 44),
          shape: const RoundedRectangleBorder(borderRadius: _interactiveRadius),
          splashFactory: InkSparkle.splashFactory,
          animationDuration: durationPress,
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
      // Glass-style card: semi-transparent background with subtle border.
      cardTheme: CardThemeData(
        color: AeluColors.glassBgDark,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: _interactiveRadius,
          side: BorderSide(color: AeluColors.glassBorderDark, width: 0.5),
        ),
        margin: const EdgeInsets.symmetric(vertical: 8),
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
      // Spring-based page transitions.
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.android: _SpringPageTransitionsBuilder(),
          TargetPlatform.macOS: _SpringPageTransitionsBuilder(),
          TargetPlatform.windows: _SpringPageTransitionsBuilder(),
          TargetPlatform.linux: _SpringPageTransitionsBuilder(),
        },
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════
//  Haptic feedback patterns aligned with brand: subtle, purposeful.
// ════════════════════════════════════════════════════════════════════════════

/// Brand-aligned haptic feedback patterns.
///
/// Each method maps to a distinct interaction type so that haptics feel
/// intentional rather than noisy.  All calls delegate to [HapticFeedback]
/// which is a no-op on platforms that lack a vibration motor.
class AeluHaptics {
  AeluHaptics._();

  /// Correct answer -- light celebratory tap.
  static void correct() => HapticFeedback.lightImpact();

  /// Incorrect answer -- medium acknowledgment.
  static void incorrect() => HapticFeedback.mediumImpact();

  /// Option selection -- subtle tick.
  static void select() => HapticFeedback.selectionClick();

  /// Button press -- light feedback.
  static void press() => HapticFeedback.lightImpact();
}

// ════════════════════════════════════════════════════════════════════════════
//  Spring page transition — upward drift with spring easing
//  Replaces FadeUpwardsPageTransitionsBuilder on non-iOS platforms.
// ════════════════════════════════════════════════════════════════════════════

/// Page transition that slides the new page up from 8px below with a spring
/// overshoot, matching the web's upward-drift + spring-ease pattern.
class _SpringPageTransitionsBuilder extends PageTransitionsBuilder {
  const _SpringPageTransitionsBuilder();

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    return _SpringPageTransition(
      routeAnimation: animation,
      secondaryRouteAnimation: secondaryAnimation,
      child: child,
    );
  }
}

class _SpringPageTransition extends StatelessWidget {
  const _SpringPageTransition({
    required this.routeAnimation,
    required this.secondaryRouteAnimation,
    required this.child,
  });

  // Spring curve: cubic-bezier(0.34, 1.56, 0.64, 1)
  static final _springCurve = CurveTween(curve: AeluTheme.springCurve);

  // Slide: 0 → 8px upward drift
  static final _offsetTween =
      Tween<Offset>(begin: const Offset(0.0, 0.02), end: Offset.zero)
          .chain(_springCurve);

  // Fade in
  static final _opacityTween =
      Tween<double>(begin: 0.0, end: 1.0).chain(CurveTween(curve: Curves.easeOut));

  // Secondary: slight scale-down for the outgoing page
  static final _secondaryScaleTween =
      Tween<double>(begin: 1.0, end: 0.98).chain(CurveTween(curve: Curves.easeOut));

  final Animation<double> routeAnimation;
  final Animation<double> secondaryRouteAnimation;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return SlideTransition(
      position: routeAnimation.drive(_offsetTween),
      child: FadeTransition(
        opacity: routeAnimation.drive(_opacityTween),
        child: ScaleTransition(
          scale: secondaryRouteAnimation.drive(_secondaryScaleTween),
          child: child,
        ),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════
//  Pressable button wrapper — applies scale(0.98) on press with spring ease
// ════════════════════════════════════════════════════════════════════════════

/// Wrap any widget (typically a button) to add press-scale feedback
/// matching the web's `:active { transform: scale(0.98) }` pattern.
///
/// ```dart
/// AeluPressable(
///   onTap: () => doSomething(),
///   child: Container( ... ),
/// )
/// ```
class AeluPressable extends StatefulWidget {
  const AeluPressable({
    super.key,
    required this.child,
    this.onTap,
    this.scale = AeluTheme.pressScale,
  });

  final Widget child;
  final VoidCallback? onTap;
  final double scale;

  @override
  State<AeluPressable> createState() => _AeluPressableState();
}

class _AeluPressableState extends State<AeluPressable>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: AeluTheme.durationPress,
      reverseDuration: AeluTheme.durationFast,
    );
    _scaleAnimation = Tween<double>(begin: 1.0, end: widget.scale).animate(
      CurvedAnimation(parent: _controller, curve: AeluTheme.springCurve),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onTapDown(TapDownDetails _) => _controller.forward();

  void _onTapUp(TapUpDetails _) {
    _controller.reverse();
    widget.onTap?.call();
  }

  void _onTapCancel() => _controller.reverse();

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: _onTapDown,
      onTapUp: _onTapUp,
      onTapCancel: _onTapCancel,
      behavior: HitTestBehavior.opaque,
      child: ScaleTransition(
        scale: _scaleAnimation,
        child: widget.child,
      ),
    );
  }
}
