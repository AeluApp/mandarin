import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/aelu_colors.dart';
import '../../theme/hanzi_style.dart';
import '../../core/animations/pressable_scale.dart';

/// Actionable return hook — shows tomorrow's review items and offers
/// to set a reminder. This is the "come back" promise.
class ReturnHook extends StatefulWidget {
  final List<dynamic> upcomingItems;

  const ReturnHook({super.key, required this.upcomingItems});

  @override
  State<ReturnHook> createState() => _ReturnHookState();
}

class _ReturnHookState extends State<ReturnHook> {
  bool _reminderSet = false;

  void _setReminder() {
    unawaited(HapticFeedback.mediumImpact());
    setState(() => _reminderSet = true);
    // In production, this would schedule a local notification via
    // flutter_local_notifications for tomorrow at the user's usual time.
    // For now, we show the confirmation state.
  }

  @override
  Widget build(BuildContext context) {
    if (widget.upcomingItems.isEmpty) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final hanziList = widget.upcomingItems
        .take(5)
        .map((item) => item is Map && item['hanzi'] is String ? item['hanzi'] as String : '')
        .where((h) => h.isNotEmpty)
        .join('  ');

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AeluColors.secondaryOf(context).withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AeluColors.secondaryOf(context).withValues(alpha: 0.15)),
      ),
      child: Column(
        children: [
          Text(
            'Tomorrow you\'ll review',
            style: theme.textTheme.bodySmall?.copyWith(
              color: AeluColors.secondaryOf(context),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            hanziList,
            style: HanziStyle.reader.copyWith(
              color: theme.textTheme.displayLarge?.color,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          if (!_reminderSet)
            PressableScale(
              onTap: _setReminder,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                decoration: BoxDecoration(
                  color: AeluColors.secondaryOf(context).withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.notifications_outlined,
                        size: 16, color: AeluColors.secondaryOf(context)),
                    const SizedBox(width: 6),
                    Text(
                      'Remind me',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: AeluColors.secondaryOf(context),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            )
          else
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.check_circle_outline,
                    size: 16, color: AeluColors.correctOf(context)),
                const SizedBox(width: 6),
                Text(
                  'Reminder set for tomorrow',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: AeluColors.correctOf(context),
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }
}
