import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// Confirm quit dialog with progress warning and warm tone.
class QuitDialog extends StatelessWidget {
  final int completed;
  final int total;

  const QuitDialog(
      {super.key, required this.completed, required this.total});

  static Future<bool> show(BuildContext context,
      {required int completed, required int total}) async {
    final result = await showModalBottomSheet<bool>(
      context: context,
      builder: (_) =>
          QuitDialog(completed: completed, total: total),
    );
    return result ?? false;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final progress = total > 0
        ? (completed / total * 100).round()
        : 0;

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle bar
          Container(
            width: 36,
            height: 4,
            decoration: BoxDecoration(
              color: AeluColors.muted.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 20),
          Text('End session?', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 12),
          if (completed > 0) ...[
            // Show progress ring mini
            Text(
              '$progress% complete',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: AeluColors.accentOf(context),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Your progress on $completed items will be saved.',
              style: theme.textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
          ] else
            Text(
              'Your session hasn\'t started yet.',
              style: theme.textTheme.bodyMedium,
            ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Keep Going'),
            ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: Text(
                'End Session',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: AeluColors.mutedOf(context),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
