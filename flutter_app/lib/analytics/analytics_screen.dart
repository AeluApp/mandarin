import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/animations/drift_up.dart';
import '../core/animations/content_switcher.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';
import 'analytics_provider.dart';

class AnalyticsScreen extends ConsumerWidget {
  const AnalyticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncState = ref.watch(analyticsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Insights')),
      body: ContentSwitcher(
        child: asyncState.when(
          loading: () => const _AnalyticsSkeleton(key: ValueKey('loading')),
          error: (err, _) => _ErrorView(
            key: const ValueKey('error'),
            onRetry: () => ref.invalidate(analyticsProvider),
          ),
          data: (data) => SingleChildScrollView(
            key: const ValueKey('data'),
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Retention overview
                DriftUp(child: _RetentionCard(data: data.retention)),
                const SizedBox(height: 20),

                // 7-day forecast
                DriftUp(
                  delay: const Duration(milliseconds: 80),
                  child: _ForecastCard(forecast: data.retention.forecast),
                ),
                const SizedBox(height: 20),

                // Reading stats
                DriftUp(
                  delay: const Duration(milliseconds: 160),
                  child: _ReadingStatsCard(stats: data.reading),
                ),
                const SizedBox(height: 20),

                // Grammar mastery
                DriftUp(
                  delay: const Duration(milliseconds: 240),
                  child: _GrammarMasteryCard(grammar: data.grammar),
                ),
                const SizedBox(height: 40),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Retention card ──

class _RetentionCard extends StatelessWidget {
  final RetentionData data;
  const _RetentionCard({required this.data});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final stageOrder = ['durable', 'stable', 'stabilizing', 'passed', 'seen', 'unseen'];
    final stageLabels = {
      'durable': 'Durable',
      'stable': 'Stable',
      'stabilizing': 'Stabilizing',
      'passed': 'Passed',
      'seen': 'Seen',
      'unseen': 'Unseen',
    };
    final stageColors = {
      'durable': AeluColors.masteryDurable,
      'stable': AeluColors.masteryStable,
      'stabilizing': AeluColors.masteryStabilizing,
      'passed': AeluColors.masteryPassed,
      'seen': AeluColors.masterySeen,
      'unseen': AeluColors.masteryUnseen,
    };

    final total = data.totalActive > 0 ? data.totalActive : 1;

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Retention', style: theme.textTheme.titleMedium),
              const Spacer(),
              if (data.overdue > 0)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: AeluColors.incorrectOf(context).withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    '${data.overdue} overdue',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: AeluColors.incorrectOf(context),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${data.totalActive} active items',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: AeluColors.mutedOf(context)),
          ),
          const SizedBox(height: 16),

          // Stacked bar
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: SizedBox(
              height: 12,
              child: Row(
                children: stageOrder
                    .where((s) => (data.stageCounts[s] ?? 0) > 0)
                    .map((s) {
                  final count = data.stageCounts[s] ?? 0;
                  return Expanded(
                    flex: count,
                    child: Container(color: stageColors[s]),
                  );
                }).toList(),
              ),
            ),
          ),
          const SizedBox(height: 12),

          // Legend
          Wrap(
            spacing: 16,
            runSpacing: 6,
            children: stageOrder
                .where((s) => (data.stageCounts[s] ?? 0) > 0)
                .map((s) {
              final count = data.stageCounts[s] ?? 0;
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: stageColors[s],
                    ),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${stageLabels[s]} ($count)',
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

// ── 7-day forecast ──

class _ForecastCard extends StatelessWidget {
  final List<ForecastDay> forecast;
  const _ForecastCard({required this.forecast});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (forecast.isEmpty) {
      return _Card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('7-Day Forecast', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('No upcoming reviews scheduled.',
                style: theme.textTheme.bodySmall),
          ],
        ),
      );
    }

    final maxItems =
        forecast.map((f) => f.itemsDue).fold(0, math.max);
    final dayLabels = ['Today', 'Tomorrow', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7'];

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('7-Day Forecast', style: theme.textTheme.titleMedium),
          const SizedBox(height: 16),
          ...forecast.take(7).toList().asMap().entries.map((entry) {
            final i = entry.key;
            final day = entry.value;
            final barFraction = maxItems > 0 ? day.itemsDue / maxItems : 0.0;
            final label = i < dayLabels.length ? dayLabels[i] : 'Day ${i + 1}';

            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  SizedBox(
                    width: 70,
                    child: Text(label, style: theme.textTheme.bodySmall),
                  ),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: SizedBox(
                        height: 8,
                        child: FractionallySizedBox(
                          alignment: Alignment.centerLeft,
                          widthFactor: barFraction.clamp(0.02, 1.0),
                          child: Container(
                            color: AeluColors.secondaryOf(context),
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  SizedBox(
                    width: 30,
                    child: Text(
                      '${day.itemsDue}',
                      style: theme.textTheme.bodySmall,
                      textAlign: TextAlign.end,
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

// ── Reading stats ──

class _ReadingStatsCard extends StatelessWidget {
  final ReadingStats stats;
  const _ReadingStatsCard({required this.stats});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Reading', style: theme.textTheme.titleMedium),
          const SizedBox(height: 16),
          Row(
            children: [
              _StatTile(
                  label: 'Total read', value: '${stats.totalPassages}'),
              _StatTile(
                  label: 'This week', value: '${stats.weekPassages}'),
              _StatTile(
                label: 'Comprehension',
                value: '${stats.comprehensionPct.round()}%',
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _StatTile(
                label: 'Words looked up',
                value: '${stats.totalWordsLookedUp}',
              ),
              _StatTile(
                label: 'Avg. time',
                value: stats.avgReadingTimeSeconds > 0
                    ? '${(stats.avgReadingTimeSeconds / 60).toStringAsFixed(1)}m'
                    : '--',
              ),
              const Expanded(child: SizedBox.shrink()),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final String label;
  final String value;
  const _StatTile({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value,
              style: theme.textTheme.titleLarge
                  ?.copyWith(color: AeluColors.accentOf(context))),
          const SizedBox(height: 2),
          Text(label,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: AeluColors.mutedOf(context))),
        ],
      ),
    );
  }
}

// ── Grammar mastery ──

class _GrammarMasteryCard extends StatelessWidget {
  final GrammarMastery grammar;
  const _GrammarMasteryCard({required this.grammar});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Grammar', style: theme.textTheme.titleMedium),
              const Spacer(),
              Text(
                '${grammar.overallStudied}/${grammar.overallTotal}',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: AeluColors.mutedOf(context)),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Overall progress bar
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: grammar.overallTotal > 0
                  ? grammar.overallStudied / grammar.overallTotal
                  : 0,
              minHeight: 6,
              backgroundColor: AeluColors.masteryUnseen,
              valueColor: AlwaysStoppedAnimation(AeluColors.secondaryOf(context)),
            ),
          ),
          const SizedBox(height: 16),

          // Per-level breakdown
          ..._buildLevelRows(context, grammar),
        ],
      ),
    );
  }

  List<Widget> _buildLevelRows(BuildContext context, GrammarMastery grammar) {
    final theme = Theme.of(context);
    final sorted = grammar.byLevel.entries.toList()
      ..sort((a, b) {
        final aInt = int.tryParse(a.key) ?? 0;
        final bInt = int.tryParse(b.key) ?? 0;
        return aInt.compareTo(bInt);
      });

    return sorted.map((entry) {
      final level = entry.key;
      final data = entry.value;
      return Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(
          children: [
            SizedBox(
              width: 50,
              child: Text('HSK $level', style: theme.textTheme.bodySmall),
            ),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  value: data.total > 0 ? data.studied / data.total : 0,
                  minHeight: 6,
                  backgroundColor: AeluColors.masteryUnseen,
                  valueColor: AlwaysStoppedAnimation(
                      AeluColors.secondaryOf(context)),
                ),
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 45,
              child: Text(
                '${data.studied}/${data.total}',
                style: theme.textTheme.bodySmall,
                textAlign: TextAlign.end,
              ),
            ),
          ],
        ),
      );
    }).toList();
  }
}

// ── Shared card wrapper ──

class _Card extends StatelessWidget {
  final Widget child;
  const _Card({required this.child});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AeluColors.surfaceAltDark : AeluColors.surfaceAltLight,
        borderRadius: BorderRadius.circular(12),
      ),
      child: child,
    );
  }
}

// ── Loading / error ──

class _AnalyticsSkeleton extends StatelessWidget {
  const _AnalyticsSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.all(20),
      child: Column(
        children: [
          SkeletonPanel(height: 160),
          SizedBox(height: 20),
          SkeletonPanel(height: 120),
          SizedBox(height: 20),
          SkeletonPanel(height: 100),
          SizedBox(height: 20),
          SkeletonPanel(height: 100),
        ],
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final VoidCallback onRetry;
  const _ErrorView({super.key, required this.onRetry});

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
            Text('Couldn\'t load insights',
                style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              'Check your connection and try again.',
              style: theme.textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
