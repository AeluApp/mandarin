import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';
import '../../core/animations/timing.dart';

/// Progressive hint reveal — slides in with warm gold accent.
class HintOverlay extends StatelessWidget {
  final String hint;

  const HintOverlay({super.key, required this.hint});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Semantics(
      label: 'Hint: $hint',
      child: AnimatedContainer(
        duration: AeluTiming.fast,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AeluColors.streakGold.withValues(alpha: isDark ? 0.14 : 0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: AeluColors.streakGold.withValues(alpha: 0.2),
          ),
        ),
        child: Row(
          children: [
            const Icon(Icons.lightbulb_outlined,
                size: 18, color: AeluColors.streakGold),
            const SizedBox(width: 10),
            Expanded(
              child: Text(hint, style: theme.textTheme.bodyMedium),
            ),
          ],
        ),
      ),
    );
  }
}
