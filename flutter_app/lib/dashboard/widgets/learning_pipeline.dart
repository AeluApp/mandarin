import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// Mastery stage definitions with display labels and color resolvers.
const _stages = [
  'encountered',
  'introduced',
  'building',
  'strong',
  'mastered',
  'needs_review',
];

const _stageLabels = {
  'encountered': 'Encountered',
  'introduced': 'Introduced',
  'building': 'Building',
  'strong': 'Strong',
  'mastered': 'Mastered',
  'needs_review': 'Needs review',
};

/// Horizontal segmented bar showing item counts across 6 mastery stages.
///
/// Each segment width is proportional to its item count. Labels with counts
/// sit below the bar. Uses [AnimatedContainer] with [Curves.easeOutCubic]
/// for smooth transitions (no bounce, matching --ease-upward).
class LearningPipeline extends StatelessWidget {
  /// Map of stage key to item count.
  /// Keys: encountered, introduced, building, strong, mastered, needs_review.
  final Map<String, int> stageCounts;

  const LearningPipeline({super.key, required this.stageCounts});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final total = stageCounts.values.fold<int>(0, (a, b) => a + b);
    final surfaceBg =
        isDark ? AeluColors.surfaceDark : AeluColors.surfaceLight;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: surfaceBg,
        borderRadius: BorderRadius.circular(8),
      ),
      child: total == 0
          ? SizedBox(
              height: 48,
              child: Center(
                child: Text(
                  'Start learning to see your progress',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: _textDimOf(context),
                  ),
                ),
              ),
            )
          : Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Segmented bar
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: SizedBox(
                    height: 24,
                    child: Row(
                      children: _stages.map((stage) {
                        final count = stageCounts[stage] ?? 0;
                        if (count == 0) return const SizedBox.shrink();
                        final fraction = count / total;
                        return Flexible(
                          flex: count,
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 300),
                            curve: Curves.easeOutCubic,
                            decoration: BoxDecoration(
                              color: _stageColor(context, stage),
                            ),
                            child: Center(
                              child: fraction > 0.08
                                  ? Text(
                                      '$count',
                                      style:
                                          theme.textTheme.bodySmall?.copyWith(
                                        color: AeluColors.onAccent,
                                        fontSize: 11,
                                        fontWeight: FontWeight.w600,
                                      ),
                                      overflow: TextOverflow.clip,
                                      maxLines: 1,
                                    )
                                  : const SizedBox.shrink(),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                ),

                const SizedBox(height: 10),

                // Labels row
                Wrap(
                  spacing: 12,
                  runSpacing: 4,
                  children: _stages.map((stage) {
                    final count = stageCounts[stage] ?? 0;
                    if (count == 0) return const SizedBox.shrink();
                    return Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: _stageColor(context, stage),
                            borderRadius: BorderRadius.circular(2),
                          ),
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '${_stageLabels[stage] ?? stage} $count',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    );
                  }).toList(),
                ),
              ],
            ),
    );
  }
}

// ── Helpers ──

Color _stageColor(BuildContext context, String stage) {
  return switch (stage) {
    'encountered' => _textDimOf(context),
    'introduced' => _textDimOf(context).withValues(alpha: 0.65),
    'building' => AeluColors.accentOf(context),
    'strong' => AeluColors.secondaryOf(context),
    'mastered' => AeluColors.correctOf(context),
    'needs_review' => AeluColors.incorrectOf(context),
    _ => _textDimOf(context),
  };
}

Color _textDimOf(BuildContext context) {
  return Theme.of(context).brightness == Brightness.dark
      ? AeluColors.textDimDark
      : AeluColors.textDimLight;
}
