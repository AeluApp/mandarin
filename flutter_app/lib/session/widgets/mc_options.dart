import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/aelu_colors.dart';
import '../../core/animations/pressable_scale.dart';

/// Multiple choice options with press animation and haptic feedback.
class McOptions extends StatelessWidget {
  final List<dynamic> options;
  final ValueChanged<int> onSelect;

  const McOptions({super.key, required this.options, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Column(
      children: List.generate(options.length, (i) {
        final label = options[i] is Map
            ? (options[i] as Map)['text']?.toString() ?? '$i'
            : options[i].toString();

        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Semantics(
            button: true,
            label: 'Option ${i + 1}: $label',
            child: PressableScale(
              onTap: () {
                HapticFeedback.selectionClick();
                onSelect(i);
              },
              child: ExcludeSemantics(
                child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 14),
                decoration: BoxDecoration(
                  color: isDark
                      ? AeluColors.surfaceAltDark
                      : AeluColors.surfaceAltLight,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isDark
                        ? AeluColors.dividerDark
                        : AeluColors.divider,
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 26,
                      height: 26,
                      decoration: BoxDecoration(
                        color: AeluColors.accentOf(context).withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Center(
                        child: Text(
                          '${i + 1}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: AeluColors.accentOf(context),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(label, style: theme.textTheme.bodyLarge),
                    ),
                  ],
                ),
              ),
            ),
          ),
          ),
        );
      }),
    );
  }
}
