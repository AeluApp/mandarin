import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/animations/pressable_scale.dart';
import '../../theme/aelu_colors.dart';

/// Media recommendation card with title, type badge, difficulty.
class MediaCard extends StatelessWidget {
  final Map<String, dynamic> item;
  final VoidCallback onWatched;
  final VoidCallback onSkip;
  final VoidCallback? onLike;

  const MediaCard({
    super.key,
    required this.item,
    required this.onWatched,
    required this.onSkip,
    this.onLike,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final title = item['title'] is String ? item['title'] as String : '';
    final type = item['type'] is String ? item['type'] as String : '';
    final level = item['level'] is String ? item['level'] as String : '';
    final description = item['description'] is String ? item['description'] as String : '';

    return Semantics(
      label: '$title - $type - $level',
      child: PressableScale(
        onTap: () {
          HapticFeedback.selectionClick();
          onWatched();
        },
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(title, style: theme.textTheme.titleMedium),
                    ),
                    if (type.isNotEmpty)
                      Chip(
                        label: Text(type, style: theme.textTheme.bodySmall),
                        padding: EdgeInsets.zero,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                  ],
                ),
                if (level.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(level, style: theme.textTheme.bodySmall),
                ],
                if (description.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(description, style: theme.textTheme.bodyMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
                ],
                const SizedBox(height: 12),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.skip_next_outlined),
                      tooltip: 'Skip',
                      onPressed: () {
                        HapticFeedback.lightImpact();
                        onSkip();
                      },
                      iconSize: 20,
                    ),
                    if (onLike != null)
                      IconButton(
                        icon: const Icon(Icons.favorite_outline),
                        tooltip: 'Like',
                        onPressed: () {
                          HapticFeedback.lightImpact();
                          onLike!();
                        },
                        iconSize: 20,
                      ),
                    IconButton(
                      icon: const Icon(Icons.check_circle_outline),
                      tooltip: 'Mark watched',
                      onPressed: () {
                        HapticFeedback.lightImpact();
                        onWatched();
                      },
                      color: AeluColors.secondaryOf(context),
                      iconSize: 20,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
