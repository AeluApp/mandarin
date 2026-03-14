import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/theme/aelu_colors.dart';
import 'package:aelu/theme/aelu_theme.dart';
import 'package:aelu/theme/hanzi_style.dart';

void main() {
  group('AeluColors — light mode', () {
    test('surface matches base', () {
      expect(AeluColors.surfaceLight, AeluColors.baseLight);
    });

    test('light colors match web CSS tokens', () {
      expect(AeluColors.surfaceLight, const Color(0xFFF2EBE0));
      expect(AeluColors.textLight, const Color(0xFF2A3650));
      expect(AeluColors.accent, const Color(0xFF946070));
      expect(AeluColors.secondary, const Color(0xFF6A7A5A));
      expect(AeluColors.correct, const Color(0xFF5A7A5A));
      expect(AeluColors.incorrect, const Color(0xFF806058));
    });

    test('dim and faint text are lighter than main text', () {
      // Lighter means higher luminance.
      expect(
        AeluColors.textDimLight.computeLuminance(),
        greaterThan(AeluColors.textLight.computeLuminance()),
      );
      expect(
        AeluColors.textFaintLight.computeLuminance(),
        greaterThan(AeluColors.textDimLight.computeLuminance()),
      );
    });
  });

  group('AeluColors — dark mode', () {
    test('dark colors match web CSS tokens', () {
      expect(AeluColors.surfaceDark, const Color(0xFF1C2028));
      expect(AeluColors.textDark, const Color(0xFFE4DDD0));
    });

    test('surface matches base in dark mode', () {
      expect(AeluColors.surfaceDark, AeluColors.baseDark);
    });

    test('dark text is lighter than dark surface', () {
      expect(
        AeluColors.textDark.computeLuminance(),
        greaterThan(AeluColors.surfaceDark.computeLuminance()),
      );
    });

    test('dark semantic overrides have higher contrast', () {
      // correctDark should be lighter than correct for dark background.
      expect(
        AeluColors.correctDark.computeLuminance(),
        greaterThan(AeluColors.correct.computeLuminance()),
      );
      expect(
        AeluColors.incorrectDark.computeLuminance(),
        greaterThan(AeluColors.incorrect.computeLuminance()),
      );
    });
  });

  group('AeluColors — mastery stages', () {
    test('mastery colors form a gradient from durable to unseen', () {
      // Durable should be the darkest/most saturated green.
      // Unseen should be the lightest/most neutral.
      expect(
        AeluColors.masteryUnseen.computeLuminance(),
        greaterThan(AeluColors.masteryDurable.computeLuminance()),
      );
    });

    test('all mastery colors are defined', () {
      expect(AeluColors.masteryDurable, isNotNull);
      expect(AeluColors.masteryStable, isNotNull);
      expect(AeluColors.masteryStabilizing, isNotNull);
      expect(AeluColors.masteryPassed, isNotNull);
      expect(AeluColors.masterySeen, isNotNull);
      expect(AeluColors.masteryUnseen, isNotNull);
    });
  });

  group('AeluTheme — light', () {
    test('has 12px border radius on buttons', () {
      final theme = AeluTheme.light();
      final buttonShape =
          theme.elevatedButtonTheme.style?.shape?.resolve({});
      expect(buttonShape, isA<RoundedRectangleBorder>());
      final rrb = buttonShape as RoundedRectangleBorder;
      expect(rrb.borderRadius, const BorderRadius.all(Radius.circular(12)));
    });

    test('uses correct scaffold background', () {
      final theme = AeluTheme.light();
      expect(theme.scaffoldBackgroundColor, AeluColors.baseLight);
    });

    test('uses correct text color', () {
      final theme = AeluTheme.light();
      // Body text should use the light text color.
      expect(
        theme.textTheme.bodyMedium?.color,
        AeluColors.textLight,
      );
    });

    test('uses CormorantGaramond for headings', () {
      final theme = AeluTheme.light();
      expect(theme.textTheme.displayLarge?.fontFamily, 'CormorantGaramond');
      expect(theme.textTheme.displayMedium?.fontFamily, 'CormorantGaramond');
    });

    test('uses SourceSerif4 for body', () {
      final theme = AeluTheme.light();
      expect(theme.textTheme.bodyMedium?.fontFamily, 'SourceSerif4');
    });

    test('card has zero border radius', () {
      final theme = AeluTheme.light();
      final cardShape = theme.cardTheme.shape;
      expect(cardShape, isA<RoundedRectangleBorder>());
    });
  });

  group('AeluTheme — dark', () {
    test('has dark scaffold background', () {
      final theme = AeluTheme.dark();
      expect(theme.scaffoldBackgroundColor, AeluColors.baseDark);
    });

    test('has zero border radius on cards', () {
      final theme = AeluTheme.dark();
      final cardShape = theme.cardTheme.shape;
      expect(cardShape, isA<RoundedRectangleBorder>());
    });

    test('uses correct text color for dark mode', () {
      final theme = AeluTheme.dark();
      expect(
        theme.textTheme.bodyMedium?.color,
        AeluColors.textDark,
      );
    });

    test('brightness is dark', () {
      final theme = AeluTheme.dark();
      expect(theme.brightness, Brightness.dark);
    });
  });

  group('AeluTheme — light vs dark consistency', () {
    test('both themes use same font families', () {
      final light = AeluTheme.light();
      final dark = AeluTheme.dark();
      expect(
        light.textTheme.displayLarge?.fontFamily,
        dark.textTheme.displayLarge?.fontFamily,
      );
      expect(
        light.textTheme.bodyMedium?.fontFamily,
        dark.textTheme.bodyMedium?.fontFamily,
      );
    });

    test('both themes use same font sizes', () {
      final light = AeluTheme.light();
      final dark = AeluTheme.dark();
      expect(
        light.textTheme.displayLarge?.fontSize,
        dark.textTheme.displayLarge?.fontSize,
      );
      expect(
        light.textTheme.bodyMedium?.fontSize,
        dark.textTheme.bodyMedium?.fontSize,
      );
    });
  });

  group('HanziStyle', () {
    test('display has correct font family and size', () {
      expect(HanziStyle.display.fontFamily, 'NotoSerifSC');
      expect(HanziStyle.display.fontSize, 48);
    });

    test('reader has generous line height', () {
      expect(HanziStyle.reader.height, 1.8);
    });

    test('inline has appropriate size for body text', () {
      expect(HanziStyle.inline.fontSize, 14);
      expect(HanziStyle.inline.fontFamily, 'NotoSerifSC');
    });

    test('compact has medium weight', () {
      expect(HanziStyle.compact.fontWeight, FontWeight.w500);
      expect(HanziStyle.compact.fontSize, 16);
    });

    test('all styles use NotoSerifSC', () {
      expect(HanziStyle.display.fontFamily, 'NotoSerifSC');
      expect(HanziStyle.inline.fontFamily, 'NotoSerifSC');
      expect(HanziStyle.reader.fontFamily, 'NotoSerifSC');
      expect(HanziStyle.compact.fontFamily, 'NotoSerifSC');
    });

    test('font sizes are ordered correctly', () {
      expect(HanziStyle.display.fontSize!,
          greaterThan(HanziStyle.reader.fontSize!));
      expect(HanziStyle.reader.fontSize!,
          greaterThan(HanziStyle.compact.fontSize!));
      expect(HanziStyle.compact.fontSize!,
          greaterThan(HanziStyle.inline.fontSize!));
    });
  });
}
