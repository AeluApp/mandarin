import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';
import '../theme/aelu_spacing.dart';
import '../core/notification_scheduler.dart';
import '../core/animations/drift_up.dart';
import '../core/animations/pressable_scale.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/horizon.dart';
import '../shared/widgets/nps_dialog.dart';
import '../theme/aelu_colors.dart';
import 'widgets/mastery_delta.dart';
import 'widgets/practiced_grid.dart';
import 'widgets/progress_ring.dart';
import 'widgets/return_hook.dart';

class CompleteScreen extends ConsumerStatefulWidget {
  final Map<String, dynamic> results;
  const CompleteScreen({super.key, required this.results});

  @override
  ConsumerState<CompleteScreen> createState() => _CompleteScreenState();
}

class _CompleteScreenState extends ConsumerState<CompleteScreen> {
  bool _showMilestone = false;

  @override
  void initState() {
    super.initState();
    unawaited(HapticFeedback.heavyImpact());
    ref.read(soundProvider).play(SoundEvent.sessionComplete);

    final accuracy = _accuracy;
    final isFirst = widget.results['is_first_session'] == true;
    final streakDays = (widget.results['streak_days'] as num?)?.toInt() ?? 0;
    final isMilestone = streakDays > 0 && (streakDays % 7 == 0 || streakDays % 30 == 0);

    // Level up / milestone celebration — differentiated sounds
    if (isFirst) {
      Future.delayed(const Duration(milliseconds: 1500), () {
        if (mounted) {
          setState(() => _showMilestone = true);
          ref.read(soundProvider).play(SoundEvent.levelUp);
        }
      });
    } else if (isMilestone) {
      Future.delayed(const Duration(milliseconds: 1500), () {
        if (mounted) {
          setState(() => _showMilestone = true);
          ref.read(soundProvider).play(SoundEvent.streakMilestone);
        }
      });
    }

    // Accuracy milestone — celebrate ≥90% accuracy
    if (accuracy >= 0.9 && !isFirst && !isMilestone) {
      Future.delayed(const Duration(milliseconds: 1200), () {
        if (mounted) {
          ref.read(soundProvider).play(SoundEvent.milestone);
        }
      });
    }

    // NPS prompt — show every 5th completed session.
    _maybeShowNps();

    // Record practice time and schedule notifications.
    _scheduleNotifications();
  }

  Future<void> _scheduleNotifications() async {
    final scheduler = ref.read(notificationSchedulerProvider);
    final streakDays = (widget.results['streak_days'] as num?)?.toInt() ?? 0;

    // Cancel today's reminders (user already practiced).
    await scheduler.cancelAll();
    await scheduler.recordPracticeTime();

    // Schedule return reminder for tomorrow.
    await scheduler.scheduleReturnReminder(
      title: 'Time to practice',
      body: 'Your next Mandarin session is waiting.',
    );

    // Schedule streak-at-risk reminder if streak is active.
    if (streakDays > 0) {
      await scheduler.scheduleStreakReminder(streakDays);
    }
  }

  Future<void> _maybeShowNps() async {
    const key = 'nps_session_count';
    const interval = 5;
    final prefs = await SharedPreferences.getInstance();
    final count = (prefs.getInt(key) ?? 0) + 1;
    await prefs.setInt(key, count);
    if (count % interval == 0 && mounted) {
      // Delay so user can enjoy the results screen first.
      await Future.delayed(const Duration(seconds: 3));
      if (mounted) {
        unawaited(NpsDialog.show(context, ref.read(apiClientProvider)));
      }
    }
  }

  void _shareResults(BuildContext context, double accuracy, int streakDays) {
    final pct = (accuracy * 100).round();
    final streakText = streakDays > 0 ? ' \u2022 $streakDays day streak' : '';
    Share.share(
      '$pct% accuracy$streakText \u2014 practicing Mandarin with Aelu. aelu.app',
    );
  }

  double get _accuracy {
    final completed =
        (widget.results['items_completed'] as num?)?.toInt() ?? 0;
    final correct = (widget.results['items_correct'] as num?)?.toInt() ?? 0;
    return completed > 0 ? correct / completed : 0.0;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final completed =
        (widget.results['items_completed'] as num?)?.toInt() ?? 0;
    final correct = (widget.results['items_correct'] as num?)?.toInt() ?? 0;
    final accuracy = _accuracy;
    final duration =
        (widget.results['duration_seconds'] as num?)?.toInt() ?? 0;
    final minutes = duration ~/ 60;
    final seconds = duration % 60;
    final practiced =
        (widget.results['practiced_items'] as List<dynamic>?) ?? [];
    final upcoming =
        (widget.results['upcoming_items'] as List<dynamic>?) ?? [];
    final streakDays =
        (widget.results['streak_days'] as num?)?.toInt() ?? 0;

    return Scaffold(
      body: Stack(
        children: [
          // Main content — pinned Done button at bottom
          SafeArea(
            child: Column(
              children: [
                // Scrollable content
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.symmetric(horizontal: 28),
                    child: Column(
                      children: [
                        const SizedBox(height: 48),

                        // ── Accuracy ring — the hero ──
                        DriftUp(
                          child: ProgressRing(value: accuracy, size: 172),
                        ),
                        const SizedBox(height: 20),

                        // ── "Session Complete" or milestone message ──
                        DriftUp(
                          delay: const Duration(milliseconds: 200),
                          child: AnimatedSwitcher(
                            duration: const Duration(milliseconds: 400),
                            child: _showMilestone
                                ? _MilestoneBanner(streakDays: streakDays)
                                : Text(
                                    'Session complete',
                                    key: const ValueKey('title'),
                                    style: theme.textTheme.displayMedium,
                                    textAlign: TextAlign.center,
                                  ),
                          ),
                        ),
                        const SizedBox(height: 24),

                        // ── Mastery delta ──
                        DriftUp(
                          delay: const Duration(milliseconds: 300),
                          child: MasteryDelta(results: widget.results),
                        ),
                        const SizedBox(height: 20),

                        // ── Stats row ──
                        DriftUp(
                          delay: const Duration(milliseconds: 350),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                            children: [
                              _ResultStat(
                                  label: 'Items', value: '$completed'),
                              _ResultStat(
                                  label: 'Correct', value: '$correct'),
                              _ResultStat(
                                  label: 'Time',
                                  value: '${minutes}m ${seconds}s'),
                            ],
                          ),
                        ),
                        const SizedBox(height: 28),

                        const Horizon(animated: true),
                        const SizedBox(height: 28),

                        // ── Practiced items — cascading entrance ──
                        if (practiced.isNotEmpty)
                          PracticedGrid(items: practiced),
                        const SizedBox(height: 28),

                        // ── Return hook — the "come back" promise ──
                        if (upcoming.isNotEmpty)
                          DriftUp(
                            delay: const Duration(milliseconds: 600),
                            child: ReturnHook(upcomingItems: upcoming),
                          ),
                        const SizedBox(height: 16),
                      ],
                    ),
                  ),
                ),

                // ── Pinned bottom actions ──
                Padding(
                  padding: const EdgeInsets.fromLTRB(28, 8, 28, 16),
                  child: Column(
                    children: [
                      // Share prompt for great sessions, milestones, or first session
                      if (accuracy >= 0.9 ||
                          widget.results['is_first_session'] == true ||
                          (streakDays > 0 && (streakDays % 7 == 0 || streakDays % 30 == 0)))
                        Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: PressableScale(
                            onTap: () {
                              HapticFeedback.selectionClick();
                              _shareResults(context, accuracy, streakDays);
                            },
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(Icons.share_outlined, size: 16, color: AeluColors.accentOf(context)),
                                const SizedBox(width: 6),
                                Text(
                                  widget.results['is_first_session'] == true
                                      ? 'Share your first session'
                                      : streakDays > 0 && (streakDays % 7 == 0 || streakDays % 30 == 0)
                                          ? 'Share your $streakDays-day streak'
                                          : 'Share your results',
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    color: AeluColors.accentOf(context),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      Row(
                        children: [
                          // Practice again
                          Expanded(
                            child: PressableScale(
                              onTap: () {
                                ref.read(soundProvider).play(SoundEvent.sessionStart);
                                context.go('/session/full');
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 16),
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(
                                    color: AeluColors.accentOf(context).withValues(alpha: 0.4),
                                  ),
                                ),
                                child: Text(
                                  'Practice again',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    color: AeluColors.accentOf(context),
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          // Done
                          Expanded(
                            child: PressableScale(
                              onTap: () {
                                ref.read(soundProvider).play(SoundEvent.navigate);
                                context.go('/');
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 16),
                                decoration: BoxDecoration(
                                  color: AeluColors.accentOf(context),
                                  borderRadius: BorderRadius.circular(12),
                                  boxShadow: [
                                    BoxShadow(
                                      color: AeluColors.accentOf(context).withValues(alpha: 0.2),
                                      blurRadius: 8,
                                      offset: const Offset(0, 3),
                                    ),
                                  ],
                                ),
                                child: Text(
                                  'Done',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    color: AeluColors.onAccent,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

        ],
      ),
    );
  }
}

class _MilestoneBanner extends StatelessWidget {
  final int streakDays;
  const _MilestoneBanner({required this.streakDays});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final message = streakDays % 30 == 0
        ? '$streakDays days!'
        : '$streakDays day streak!';

    return Column(
      children: [
        const Icon(Icons.local_fire_department,
            color: AeluColors.streakGold, size: 32),
        const SizedBox(height: 8),
        Text(
          message,
          key: const ValueKey('milestone'),
          style: theme.textTheme.displayMedium?.copyWith(
            color: AeluColors.streakGold,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

class _ResultStat extends StatelessWidget {
  final String label;
  final String value;
  const _ResultStat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Semantics(
      label: '$label: $value',
      child: Column(
        children: [
          Text(value, style: theme.textTheme.headlineMedium),
          const SizedBox(height: 2),
          Text(label, style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}
