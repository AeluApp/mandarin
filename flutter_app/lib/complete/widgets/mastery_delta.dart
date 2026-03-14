import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// Before/after mastery comparison — pill-shaped chips with warm colors.
class MasteryDelta extends StatelessWidget {
  final Map<String, dynamic> results;

  const MasteryDelta({super.key, required this.results});

  @override
  Widget build(BuildContext context) {
    final promoted = (results['items_promoted'] as num?)?.toInt() ?? 0;
    final demoted = (results['items_demoted'] as num?)?.toInt() ?? 0;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (promoted == 0 && demoted == 0) return const SizedBox.shrink();

    final correctColor = isDark ? AeluColors.correctDark : AeluColors.correct;
    final incorrectColor = isDark ? AeluColors.incorrectDark : AeluColors.incorrect;

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (promoted > 0)
          _DeltaChip(
            icon: Icons.trending_up_rounded,
            value: '+$promoted',
            color: correctColor,
            label: 'mastered',
          ),
        if (promoted > 0 && demoted > 0) const SizedBox(width: 12),
        if (demoted > 0)
          _DeltaChip(
            icon: Icons.trending_down_rounded,
            value: '-$demoted',
            color: incorrectColor,
            label: 'review',
          ),
      ],
    );
  }
}

class _DeltaChip extends StatelessWidget {
  final IconData icon;
  final String value;
  final Color color;
  final String label;
  const _DeltaChip({
    required this.icon,
    required this.value,
    required this.color,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Semantics(
      label: '$value items $label',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withValues(alpha: 0.2)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 6),
            Text(
              value,
              style: theme.textTheme.titleMedium?.copyWith(
                color: color,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(width: 4),
            Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(
                color: color.withValues(alpha: 0.7),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
