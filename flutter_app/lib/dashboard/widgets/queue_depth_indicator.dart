import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// Horizontal utilization bar showing queue depth relative to capacity.
///
/// Color shifts based on utilization:
/// - Healthy (<=60%): [AeluColors.correct] (sage green)
/// - Heavy (61-85%): [AeluColors.accent] (bougainvillea)
/// - Near capacity (>85%): [AeluColors.incorrect] (warm brown)
///
/// Uses [AnimatedContainer] with [Curves.easeOutCubic] for fill animation
/// (no bounce, matching --ease-upward).
class QueueDepthIndicator extends StatelessWidget {
  final int current;
  final int limit;
  final String health;
  final String? recommendation;

  const QueueDepthIndicator({
    super.key,
    required this.current,
    required this.limit,
    required this.health,
    this.recommendation,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final fraction = limit > 0 ? (current / limit).clamp(0.0, 1.0) : 0.0;
    final fillColor = _utilizationColor(context, fraction);
    final trackColor = isDark ? AeluColors.dividerDark : AeluColors.divider;
    final dimColor = _textDimOf(context);

    return Semantics(
      label: 'Queue: $current of $limit items, $health',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header: "Queue: X / Y items"
          Text(
            'Queue: $current / $limit items',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 8),

          // Bar track + fill
          SizedBox(
            height: 8,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: Stack(
                children: [
                  // Track
                  Container(
                    decoration: BoxDecoration(
                      color: trackColor,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  // Fill
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeOutCubic,
                    width: double.infinity,
                    alignment: Alignment.centerLeft,
                    child: FractionallySizedBox(
                      widthFactor: fraction,
                      child: Container(
                        decoration: BoxDecoration(
                          color: fillColor,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 6),

          // Health label + recommendation
          Row(
            children: [
              Text(
                health,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: fillColor,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (recommendation != null) ...[
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    recommendation!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: dimColor,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

// ── Helpers ──

Color _utilizationColor(BuildContext context, double fraction) {
  final pct = fraction * 100;
  if (pct > 85) return AeluColors.incorrectOf(context);
  if (pct > 60) return AeluColors.accentOf(context);
  return AeluColors.correctOf(context);
}

Color _textDimOf(BuildContext context) {
  return Theme.of(context).brightness == Brightness.dark
      ? AeluColors.textDimDark
      : AeluColors.textDimLight;
}
