import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

enum SnackbarType { success, error, info }

/// Styled snackbar utility — replaces all raw ScaffoldMessenger calls.
///
/// Uses theme colors, zero border radius, DriftUp-style entrance.
class AeluSnackbar {
  AeluSnackbar._();

  static void show(
    BuildContext context,
    String message, {
    SnackbarType type = SnackbarType.info,
  }) {
    final colors = _colorsForType(context, type);

    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(
        SnackBar(
          content: Row(
            children: [
              if (colors.$2 != null) ...[
                Icon(colors.$2, size: 18, color: AeluColors.onAccent),
                const SizedBox(width: 10),
              ],
              Expanded(
                child: Text(
                  message,
                  style: const TextStyle(
                    fontFamily: 'SourceSerif4',
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: AeluColors.onAccent,
                  ),
                ),
              ),
            ],
          ),
          backgroundColor: colors.$1,
          behavior: SnackBarBehavior.floating,
          shape: const RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(12)),
          ),
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          duration: const Duration(seconds: 3),
          dismissDirection: DismissDirection.horizontal,
        ),
      );
  }

  static (Color, IconData?) _colorsForType(BuildContext context, SnackbarType type) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    switch (type) {
      case SnackbarType.success:
        return (isDark ? AeluColors.correctDark : AeluColors.correct,
            Icons.check_circle_outline);
      case SnackbarType.error:
        return (isDark ? AeluColors.incorrectDark : AeluColors.incorrect,
            Icons.error_outline);
      case SnackbarType.info:
        return (
          isDark ? AeluColors.surfaceAltDark : AeluColors.textLight,
          null,
        );
    }
  }
}
