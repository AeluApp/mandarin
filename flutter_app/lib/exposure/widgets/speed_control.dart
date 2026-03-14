import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/aelu_colors.dart';
import '../../core/animations/pressable_scale.dart';

/// Playback speed control — 0.5x to 1.5x with pill-shaped selectors.
class SpeedControl extends StatelessWidget {
  final double speed;
  final ValueChanged<double> onChanged;

  const SpeedControl(
      {super.key, required this.speed, required this.onChanged});

  static const _speeds = [0.5, 0.75, 1.0, 1.25, 1.5];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Semantics(
      label: 'Playback speed ${speed}x',
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: _speeds.map((s) {
          final selected = (s - speed).abs() < 0.01;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 3),
            child: PressableScale(
              onTap: () {
                HapticFeedback.selectionClick();
                onChanged(s);
              },
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                height: 44,
                padding:
                    const EdgeInsets.symmetric(horizontal: 14),
                decoration: BoxDecoration(
                  color: selected
                      ? (isDark ? AeluColors.accentDark : AeluColors.accent).withValues(alpha: 0.12)
                      : (isDark
                          ? AeluColors.surfaceAltDark
                          : AeluColors.surfaceAltLight),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: selected
                        ? (isDark ? AeluColors.accentDark : AeluColors.accent).withValues(alpha: 0.4)
                        : (isDark
                            ? AeluColors.dividerDark
                            : AeluColors.divider),
                  ),
                ),
                child: Center(
                  child: Text(
                    '${s}x',
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight:
                          selected ? FontWeight.w700 : FontWeight.w400,
                      color: selected ? (isDark ? AeluColors.accentDark : AeluColors.accent) : null,
                    ),
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}
