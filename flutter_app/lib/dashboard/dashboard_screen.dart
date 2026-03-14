import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../theme/aelu_colors.dart';
import '../theme/aelu_spacing.dart';
import '../theme/hanzi_style.dart';
import '../shared/widgets/offline_banner.dart';
import '../shared/widgets/skeleton.dart';
import '../core/animations/content_switcher.dart';
import '../core/animations/drift_up.dart';
import '../core/animations/pressable_scale.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import 'dashboard_provider.dart';
import 'widgets/mastery_bars.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashState = ref.watch(dashboardProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: ContentSwitcher(
        child: dashState.when(
          loading: () => const DashboardSkeleton(),
          error: (err, _) => _ErrorView(
          onRetry: () => ref.invalidate(dashboardProvider),
        ),
        data: (data) => SafeArea(
          child: Column(
            children: [
              // Offline banner
              const OfflineBanner(),

              // ── Top bar: ambient stats + settings ──
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                child: Row(
                  children: [
                    // Streak — animated when at milestone
                    _StreakDisplay(
                      days: data.streakDays,
                      momentum: data.momentum,
                    ),
                    const Spacer(),
                    if (data.recentAccuracy > 0)
                      Padding(
                        padding: const EdgeInsets.only(right: 12),
                        child: Text(
                          '${data.recentAccuracy}%',
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                    Semantics(
                      button: true,
                      label: 'Settings',
                      child: PressableScale(
                        onTap: () {
                          ref.read(soundProvider).play(SoundEvent.navigate);
                          context.push('/settings');
                        },
                        child: const Padding(
                          padding: EdgeInsets.all(11),
                          child: Icon(Icons.settings_outlined, size: 22),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              // ── Resume banner (if session was interrupted) ──
              if (data.momentum == 'resumable')
                _ResumeBanner(
                  onResume: () {
                    ref.read(soundProvider).play(SoundEvent.navigate);
                    context.go('/session/full');
                  },
                ),

              // ── Scrollable content with pull-to-refresh ──
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () async {
                    unawaited(HapticFeedback.mediumImpact());
                    ref.invalidate(dashboardProvider);
                    // Wait for the provider to reload.
                    await ref.read(dashboardProvider.future);
                  },
                  child: CustomScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    slivers: [
                      // Center: the CTA
                      SliverFillRemaining(
                        hasScrollBody: false,
                        child: Column(
                          children: [
                            // ── Center: the CTA ──
                            Expanded(
                              flex: 3,
                              child: DriftUp(
                                child: Center(
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      // Upcoming hanzi preview
                                      if (data.upcomingItems.isNotEmpty) ...[
                                        Text(
                                          data.upcomingItems
                                              .take(3)
                                              .map((i) => i['hanzi'] is String ? i['hanzi'] as String : '')
                                              .where((h) => h.isNotEmpty)
                                              .join('  '),
                                          style: HanziStyle.display.copyWith(
                                            color: theme.textTheme.displayLarge?.color
                                                ?.withValues(alpha: 0.25),
                                          ),
                                        ),
                                        const SizedBox(height: 24),
                                      ],

                                      // Primary session button — ALIVE
                                      Hero(
                                        tag: 'practice_cta',
                                        child: _PracticeCTA(
                                          streakDays: data.streakDays,
                                          onTap: () {
                                            ref.read(soundProvider).play(SoundEvent.sessionStart);
                                            context.go('/session/full');
                                          },
                                        ),
                                      ),
                                      const SizedBox(height: 20),

                                      // Quick session
                                      PressableScale(
                                        onTap: () {
                                          ref.read(soundProvider).play(SoundEvent.navigate);
                                          context.go('/session/mini');
                                        },
                                        child: Semantics(
                                          button: true,
                                          label: 'Quick session, about 5 minutes',
                                          child: Padding(
                                            padding: const EdgeInsets.symmetric(
                                                horizontal: 24, vertical: 8),
                                            child: Text(
                                              'Quick session (~5 min)',
                                              style: theme.textTheme.bodyMedium?.copyWith(
                                                color: AeluColors.mutedOf(context),
                                              ),
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),

                            // ── Bottom: mastery + exposure ──
                            DriftUp(
                              delay: const Duration(milliseconds: 150),
                              child: Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 20),
                                child: Column(
                                  children: [
                                    if (data.mastery.isNotEmpty)
                                      MasteryBars(mastery: data.mastery),
                                    const SizedBox(height: 20),
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                                      children: [
                                        _ExposureLink(
                                          label: 'Read',
                                          subtitle: 'Graded stories',
                                          icon: Icons.menu_book_outlined,
                                          heroTag: 'exposure_read',
                                          onTap: () => context.go('/reading'),
                                        ),
                                        _ExposureLink(
                                          label: 'Listen',
                                          subtitle: 'Native audio',
                                          icon: Icons.headphones_outlined,
                                          heroTag: 'exposure_listen',
                                          onTap: () => context.go('/listening'),
                                        ),
                                        _ExposureLink(
                                          label: 'Watch',
                                          subtitle: 'Video picks',
                                          icon: Icons.movie_outlined,
                                          heroTag: 'exposure_watch',
                                          onTap: () => context.go('/media'),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 12),
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                                      children: [
                                        _ExposureLink(
                                          label: 'Grammar',
                                          subtitle: 'Lesson flow',
                                          icon: Icons.school_outlined,
                                          heroTag: 'exposure_grammar',
                                          onTap: () => context.go('/grammar'),
                                        ),
                                        _ExposureLink(
                                          label: 'Insights',
                                          subtitle: 'Retention & stats',
                                          icon: Icons.insights_outlined,
                                          heroTag: 'exposure_insights',
                                          onTap: () => context.go('/analytics'),
                                        ),
                                        // Spacer to keep alignment
                                        const SizedBox(width: 88, height: 72),
                                      ],
                                    ),
                                    const SizedBox(height: 20),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
      ),
    );
  }
}

// ── Streak display — rhythm pattern, not fragile counter ──

class _StreakDisplay extends StatelessWidget {
  final int days;
  final String momentum;
  const _StreakDisplay({required this.days, required this.momentum});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (days <= 0) return const SizedBox.shrink();

    // Show "X of 7 this week" rhythm pattern instead of a fragile counter.
    final daysThisWeek = days > 7 ? 7 : days;

    return Semantics(
      label: '$daysThisWeek of 7 days this week',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 7-dot rhythm indicator — filled for active days
          ...List.generate(7, (i) {
            final active = i < daysThisWeek;
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 1.5),
              child: Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: active
                      ? AeluColors.streakGold
                      : (theme.brightness == Brightness.dark
                          ? AeluColors.mutedDark
                          : AeluColors.muted).withValues(alpha: 0.3),
                ),
              ),
            );
          }),
          const SizedBox(width: 6),
          Text(
            '$daysThisWeek of 7',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

// ── Resume banner ──

class _ResumeBanner extends StatelessWidget {
  final VoidCallback onResume;
  const _ResumeBanner({required this.onResume});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PressableScale(
      onTap: onResume,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: AeluColors.accent.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AeluColors.accent.withValues(alpha: 0.2)),
        ),
        child: Row(
          children: [
            const Icon(Icons.play_arrow_rounded,
                color: AeluColors.accent, size: 20),
            const SizedBox(width: 8),
            Text('Continue where you left off',
                style: theme.textTheme.bodyMedium),
            const Spacer(),
            Icon(Icons.chevron_right,
                color: AeluColors.mutedOf(context), size: 18),
          ],
        ),
      ),
    );
  }
}

// ── Practice CTA — the emotional center ──

class _PracticeCTA extends StatefulWidget {
  final VoidCallback onTap;
  final int streakDays;
  const _PracticeCTA({required this.onTap, required this.streakDays});

  @override
  State<_PracticeCTA> createState() => _PracticeCTAState();
}

class _PracticeCTAState extends State<_PracticeCTA>
    with TickerProviderStateMixin {
  late final AnimationController _glowController;
  late final AnimationController _pressController;
  late final Animation<double> _glowOpacity;
  late final Animation<double> _pressScale;

  @override
  void initState() {
    super.initState();

    // Subtle glow pulse — the button breathes
    _glowController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat(reverse: true);
    _glowOpacity = Tween<double>(begin: 0.15, end: 0.35).animate(
      CurvedAnimation(parent: _glowController, curve: Curves.easeInOut),
    );

    // Press scale
    _pressController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 120),
    );
    _pressScale = Tween<double>(begin: 1.0, end: 0.94).animate(
      CurvedAnimation(parent: _pressController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _glowController.dispose();
    _pressController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      label: 'Start practice session',
      child: Focus(
        onKeyEvent: (node, event) {
          if (event is KeyDownEvent &&
              (event.logicalKey == LogicalKeyboardKey.enter ||
               event.logicalKey == LogicalKeyboardKey.space)) {
            unawaited(HapticFeedback.mediumImpact());
            widget.onTap();
            return KeyEventResult.handled;
          }
          return KeyEventResult.ignored;
        },
        child: Builder(
          builder: (focusContext) {
            final hasFocus = Focus.of(focusContext).hasFocus;
            return GestureDetector(
              onTapDown: (_) => _pressController.forward(),
              onTapUp: (_) => _pressController.reverse(),
              onTapCancel: () => _pressController.reverse(),
              onTap: () {
                unawaited(HapticFeedback.mediumImpact());
                widget.onTap();
              },
              child: AnimatedBuilder(
                animation: Listenable.merge([_glowController, _pressController]),
                builder: (context, child) {
                  return Transform.scale(
                    scale: _pressScale.value,
                    child: Container(
                      width: 172,
                      height: 172,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: const RadialGradient(
                          center: Alignment(-0.2, -0.3),
                          radius: 0.9,
                          colors: [
                            AeluColors.accentLight,
                            AeluColors.accent,
                            AeluColors.accentDeep,
                          ],
                          stops: [0.0, 0.5, 1.0],
                        ),
                        boxShadow: [
                          // Outer glow — breathes
                          BoxShadow(
                            color: AeluColors.accent.withValues(alpha: _glowOpacity.value),
                            blurRadius: 32,
                            spreadRadius: 4,
                          ),
                          // Depth shadow
                          BoxShadow(
                            color: AeluColors.accent.withValues(alpha: 0.25),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                          ),
                          // Focus ring — visible when keyboard-focused
                          if (hasFocus)
                            BoxShadow(
                              color: AeluColors.onAccent.withValues(alpha: 0.6),
                              blurRadius: 0,
                              spreadRadius: 3,
                            ),
                        ],
                      ),
                      child: Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              'Practice',
                              style: theme.textTheme.titleLarge?.copyWith(
                                color: AeluColors.onAccent,
                                fontSize: 21,
                              ),
                            ),
                            if (widget.streakDays > 0) ...[
                              const SizedBox(height: 4),
                              Text(
                                'Day ${widget.streakDays + 1}',
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: AeluColors.onAccent.withValues(alpha: 0.7),
                                  fontSize: 11,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            );
          },
        ),
      ),
    );
  }
}

// ── Exposure links ──

class _ExposureLink extends ConsumerWidget {
  final String label;
  final String? subtitle;
  final IconData icon;
  final String heroTag;
  final VoidCallback onTap;
  const _ExposureLink(
      {required this.label, this.subtitle, required this.icon, required this.heroTag, required this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    return Semantics(
      button: true,
      label: subtitle != null ? '$label — $subtitle' : label,
      child: Hero(
        tag: heroTag,
        child: PressableScale(
          onTap: () {
            ref.read(soundProvider).play(SoundEvent.navigate);
            onTap();
          },
          child: ExcludeSemantics(
            child: SizedBox(
              width: 88,
              height: 72,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(icon, size: 22,
                      color: isDark ? AeluColors.mutedDark : AeluColors.muted),
                  const SizedBox(height: 4),
                  Text(label, style: theme.textTheme.bodySmall),
                  if (subtitle != null)
                    Text(subtitle!, style: theme.textTheme.bodySmall?.copyWith(
                      fontSize: 10,
                      color: AeluColors.mutedOf(context),
                    )),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ── Error view ──

class _ErrorView extends StatelessWidget {
  final VoidCallback onRetry;
  const _ErrorView({required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_outlined, size: 56,
                color: AeluColors.mutedOf(context)),
            const SizedBox(height: 16),
            Text('Couldn\'t connect to Aelu',
                style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('Check your connection and try again.',
                style: theme.textTheme.bodySmall),
            const SizedBox(height: 20),
            OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
