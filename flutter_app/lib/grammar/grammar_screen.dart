import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/animations/drift_up.dart';
import '../core/animations/content_switcher.dart';
import '../core/animations/pressable_scale.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';
import '../theme/hanzi_style.dart';
import 'grammar_provider.dart';

class GrammarScreen extends ConsumerStatefulWidget {
  const GrammarScreen({super.key});

  @override
  ConsumerState<GrammarScreen> createState() => _GrammarScreenState();
}

class _GrammarScreenState extends ConsumerState<GrammarScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  int _selectedLevel = 1;

  static const _levels = [1, 2, 3, 4, 5, 6, 7, 8, 9];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: _levels.length, vsync: this);
    _tabController.addListener(_onTabChanged);
    ref.read(soundProvider).play(SoundEvent.transitionIn);
    _load();
  }

  void _onTabChanged() {
    if (_tabController.indexIsChanging) return;
    setState(() => _selectedLevel = _levels[_tabController.index]);
    ref.read(grammarProvider.notifier).loadLevel(_selectedLevel);
  }

  void _load() {
    ref.read(grammarProvider.notifier).loadLevel(_selectedLevel);
    ref.read(grammarProvider.notifier).loadMastery();
  }

  @override
  void dispose() {
    _tabController.removeListener(_onTabChanged);
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(grammarProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Grammar'),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          tabs: _levels.map((l) {
            final mastery = state.masteryByLevel[l];
            return Tab(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('HSK $l'),
                  if (mastery != null && mastery.total > 0) ...[
                    const SizedBox(width: 6),
                    _MasteryDot(pct: mastery.pct),
                  ],
                ],
              ),
            );
          }).toList(),
        ),
      ),
      body: ContentSwitcher(
        child: state.loading
            ? const _GrammarSkeleton(key: ValueKey('loading'))
            : state.error != null
                ? _ErrorView(
                    key: const ValueKey('error'),
                    message: state.error!,
                    onRetry: _load,
                  )
                : state.points.isEmpty
                    ? _EmptyView(key: const ValueKey('empty'), level: _selectedLevel)
                    : ListView.builder(
                        key: ValueKey('list-$_selectedLevel'),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 20, vertical: 16),
                        itemCount: state.points.length,
                        itemBuilder: (context, index) {
                          final point = state.points[index];
                          return DriftUp(
                            delay: Duration(
                                milliseconds: (index * 40).clamp(0, 400)),
                            child: _GrammarCard(
                              point: point,
                              onTap: () {
                                ref
                                    .read(soundProvider)
                                    .play(SoundEvent.navigate);
                                context.push('/grammar/${point.id}');
                              },
                            ),
                          );
                        },
                      ),
      ),
    );
  }
}

class _MasteryDot extends StatelessWidget {
  final double pct;
  const _MasteryDot({required this.pct});

  @override
  Widget build(BuildContext context) {
    final color = pct >= 80
        ? AeluColors.correctOf(context)
        : pct >= 40
            ? AeluColors.secondaryOf(context)
            : AeluColors.mutedOf(context);
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(shape: BoxShape.circle, color: color),
    );
  }
}

class _GrammarCard extends StatelessWidget {
  final GrammarPoint point;
  final VoidCallback onTap;
  const _GrammarCard({required this.point, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: PressableScale(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: isDark ? AeluColors.surfaceAltDark : AeluColors.surfaceAltLight,
            borderRadius: BorderRadius.circular(12),
            border: point.studied
                ? Border.all(
                    color: AeluColors.correctOf(context).withValues(alpha: 0.3))
                : null,
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            point.name,
                            style: theme.textTheme.titleSmall,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (point.studied) ...[
                          const SizedBox(width: 8),
                          Icon(Icons.check_circle_outline,
                              size: 16,
                              color: AeluColors.correctOf(context)),
                        ],
                      ],
                    ),
                    if (point.nameZh.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        point.nameZh,
                        style: HanziStyle.inline.copyWith(
                          color: AeluColors.mutedOf(context),
                        ),
                      ),
                    ],
                    const SizedBox(height: 6),
                    _CategoryChip(category: point.category),
                  ],
                ),
              ),
              Icon(Icons.chevron_right,
                  color: AeluColors.mutedOf(context), size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

class _CategoryChip extends StatelessWidget {
  final String category;
  const _CategoryChip({required this.category});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: AeluColors.accent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        category,
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: AeluColors.accentOf(context),
              fontSize: 11,
            ),
      ),
    );
  }
}

class _GrammarSkeleton extends StatelessWidget {
  const _GrammarSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: List.generate(
          5,
          (_) => const Padding(
            padding: EdgeInsets.only(bottom: 12),
            child: SkeletonPanel(height: 80),
          ),
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorView(
      {super.key, required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline,
                size: 56, color: AeluColors.mutedOf(context)),
            const SizedBox(height: 16),
            Text(message, style: theme.textTheme.titleMedium),
            const SizedBox(height: 20),
            OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

class _EmptyView extends StatelessWidget {
  final int level;
  const _EmptyView({super.key, required this.level});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('文', style: HanziStyle.display.copyWith(
              color: AeluColors.mutedOf(context),
              fontSize: 56,
            )),
            const SizedBox(height: 16),
            Text('No grammar points for HSK $level yet',
                style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              'Grammar points are loaded from the server. Check back later.',
              style: theme.textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
