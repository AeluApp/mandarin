import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';
import '../../theme/hanzi_style.dart';

/// Bottom sheet popup for word lookup — pinyin, english, audio, stage.
class WordPopup extends StatelessWidget {
  final Map<String, dynamic> data;

  const WordPopup({super.key, required this.data});

  static Future<void> show(BuildContext context, Map<String, dynamic> data) {
    return showModalBottomSheet(
      context: context,
      builder: (_) => WordPopup(data: data),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hanzi = data['hanzi'] is String ? data['hanzi'] as String : '';
    final pinyin = data['pinyin'] is String ? data['pinyin'] as String : '';
    final english = data['english'] is String ? data['english'] as String : '';
    final stage = data['stage'] is String ? data['stage'] as String : '';

    return Semantics(
      label: '$hanzi: $pinyin, $english',
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Handle bar
            Center(
              child: Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: AeluColors.muted.withValues(alpha: 0.3),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Text(hanzi, style: HanziStyle.display),
            const SizedBox(height: 12),
            Text(
              pinyin,
              style: theme.textTheme.bodyLarge?.copyWith(color: AeluColors.mutedOf(context)),
            ),
            const SizedBox(height: 12),
            Text(english, style: theme.textTheme.bodyLarge),
            if (stage.isNotEmpty) ...[
              const SizedBox(height: 16),
              Chip(label: Text(stage)),
            ],
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}
