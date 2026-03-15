import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:audioplayers/audioplayers.dart';

import '../config.dart';
import '../core/animations/drift_up.dart';
import '../core/animations/content_switcher.dart';
import '../core/animations/pressable_scale.dart';
import '../core/error_handler.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';
import '../theme/hanzi_style.dart';
import 'grammar_provider.dart';

class GrammarDetailScreen extends ConsumerStatefulWidget {
  final int pointId;
  const GrammarDetailScreen({super.key, required this.pointId});

  @override
  ConsumerState<GrammarDetailScreen> createState() =>
      _GrammarDetailScreenState();
}

class _GrammarDetailScreenState extends ConsumerState<GrammarDetailScreen> {
  final AudioPlayer _player = AudioPlayer();

  @override
  void initState() {
    super.initState();
    ref.read(grammarProvider.notifier).loadPoint(widget.pointId);
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _playExample(String chinese) async {
    unawaited(HapticFeedback.selectionClick());
    try {
      final encoded = Uri.encodeQueryComponent(chinese);
      await _player.play(UrlSource('${AppConfig.apiUrl}/api/tts?text=$encoded'));
    } catch (e, st) {
      ErrorHandler.log('Grammar play example', e, st);
    }
  }

  Future<void> _markStudied() async {
    unawaited(HapticFeedback.mediumImpact());
    final success =
        await ref.read(grammarProvider.notifier).markStudied(widget.pointId);
    if (mounted) {
      if (success) {
        ref.read(soundProvider).play(SoundEvent.sessionComplete);
        AeluSnackbar.show(context, 'Marked as studied',
            type: SnackbarType.success);
      } else {
        AeluSnackbar.show(context, 'Couldn\'t save. Try again.',
            type: SnackbarType.error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(grammarProvider);
    final point = state.selectedPoint;
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Grammar')),
      body: ContentSwitcher(
        child: state.loading
            ? const _DetailSkeleton(key: ValueKey('loading'))
            : state.error != null
                ? Center(
                    key: const ValueKey('error'),
                    child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.error_outline,
                              size: 56,
                              color: AeluColors.mutedOf(context)),
                          const SizedBox(height: 16),
                          Text(state.error!,
                              style: theme.textTheme.titleMedium),
                          const SizedBox(height: 20),
                          OutlinedButton(
                            onPressed: () => ref
                                .read(grammarProvider.notifier)
                                .loadPoint(widget.pointId),
                            child: const Text('Retry'),
                          ),
                        ],
                      ),
                    ),
                  )
                : point == null
                    ? const SizedBox.shrink(key: ValueKey('empty'))
                    : SingleChildScrollView(
                        key: const ValueKey('detail'),
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Title
                            DriftUp(
                              child: Text(point.name,
                                  style: theme.textTheme.headlineMedium),
                            ),
                            if (point.nameZh.isNotEmpty) ...[
                              const SizedBox(height: 4),
                              DriftUp(
                                delay: const Duration(milliseconds: 30),
                                child: Text(
                                  point.nameZh,
                                  style: HanziStyle.reader.copyWith(
                                    color: AeluColors.mutedOf(context),
                                  ),
                                ),
                              ),
                            ],
                            const SizedBox(height: 8),
                            DriftUp(
                              delay: const Duration(milliseconds: 60),
                              child: Row(
                                children: [
                                  Chip(label: Text('HSK ${point.hskLevel}')),
                                  const SizedBox(width: 8),
                                  _CategoryChip(category: point.category),
                                ],
                              ),
                            ),

                            // Description
                            const SizedBox(height: 24),
                            DriftUp(
                              delay: const Duration(milliseconds: 90),
                              child: Text(
                                point.description,
                                style: theme.textTheme.bodyLarge
                                    ?.copyWith(height: 1.6),
                              ),
                            ),

                            // Examples
                            if (point.examples.isNotEmpty) ...[
                              const SizedBox(height: 32),
                              DriftUp(
                                delay: const Duration(milliseconds: 120),
                                child: Text('Examples',
                                    style: theme.textTheme.titleMedium),
                              ),
                              const SizedBox(height: 12),
                              ...point.examples.asMap().entries.map((entry) {
                                final i = entry.key;
                                final ex = entry.value;
                                return DriftUp(
                                  delay: Duration(
                                      milliseconds: 150 + i * 40),
                                  child: _ExampleCard(
                                    example: ex,
                                    onPlay: () => _playExample(ex.chinese),
                                  ),
                                );
                              }),
                            ],

                            // Related vocabulary
                            if (point.relatedVocab.isNotEmpty) ...[
                              const SizedBox(height: 32),
                              DriftUp(
                                delay: const Duration(milliseconds: 200),
                                child: Text('Related Vocabulary',
                                    style: theme.textTheme.titleMedium),
                              ),
                              const SizedBox(height: 12),
                              ...point.relatedVocab
                                  .asMap()
                                  .entries
                                  .map((entry) {
                                final i = entry.key;
                                final v = entry.value;
                                return DriftUp(
                                  delay: Duration(
                                      milliseconds: 230 + i * 30),
                                  child: _VocabRow(vocab: v),
                                );
                              }),
                            ],

                            // Actions
                            const SizedBox(height: 40),
                            DriftUp(
                              delay: const Duration(milliseconds: 300),
                              child: Column(
                                children: [
                                  if (!point.studied)
                                    SizedBox(
                                      width: double.infinity,
                                      child: PressableScale(
                                        onTap: _markStudied,
                                        child: Container(
                                          padding: const EdgeInsets
                                              .symmetric(vertical: 16),
                                          decoration: BoxDecoration(
                                            color: AeluColors.accent,
                                            borderRadius:
                                                BorderRadius.circular(12),
                                          ),
                                          child: Text(
                                            'Mark as Studied',
                                            style: theme
                                                .textTheme.titleMedium
                                                ?.copyWith(
                                                    color:
                                                        AeluColors.onAccent),
                                            textAlign: TextAlign.center,
                                          ),
                                        ),
                                      ),
                                    )
                                  else
                                    Row(
                                      children: [
                                        Icon(Icons.check_circle,
                                            color: AeluColors.correctOf(
                                                context)),
                                        const SizedBox(width: 8),
                                        Text(
                                          'Studied',
                                          style: theme.textTheme.bodyMedium
                                              ?.copyWith(
                                                  color:
                                                      AeluColors.correctOf(
                                                          context)),
                                        ),
                                      ],
                                    ),
                                  const SizedBox(height: 12),
                                  SizedBox(
                                    width: double.infinity,
                                    child: OutlinedButton.icon(
                                      onPressed: () {
                                        ref
                                            .read(soundProvider)
                                            .play(SoundEvent.navigate);
                                        context.go('/session/full');
                                      },
                                      icon: const Icon(
                                          Icons.play_arrow_rounded),
                                      label: const Text(
                                          'Practice This Grammar'),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 40),
                          ],
                        ),
                      ),
      ),
    );
  }
}

class _ExampleCard extends StatelessWidget {
  final GrammarExample example;
  final VoidCallback onPlay;
  const _ExampleCard({required this.example, required this.onPlay});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isDark
              ? AeluColors.surfaceAltDark
              : AeluColors.surfaceAltLight,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    example.chinese,
                    style: HanziStyle.compact.copyWith(fontSize: 20),
                  ),
                ),
                PressableScale(
                  onTap: onPlay,
                  child: Semantics(
                    button: true,
                    label: 'Play audio for ${example.chinese}',
                    child: Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: AeluColors.accent.withValues(alpha: 0.1),
                      ),
                      child: Icon(Icons.volume_up_outlined,
                          size: 18, color: AeluColors.accentOf(context)),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              example.pinyin,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: AeluColors.mutedOf(context)),
            ),
            const SizedBox(height: 4),
            Text(example.english, style: theme.textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}

class _VocabRow extends StatelessWidget {
  final GrammarVocab vocab;
  const _VocabRow({required this.vocab});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    Color stageColor;
    switch (vocab.stage) {
      case 'durable':
        stageColor = AeluColors.masteryDurable;
        break;
      case 'stable':
        stageColor = AeluColors.masteryStable;
        break;
      case 'stabilizing':
        stageColor = AeluColors.masteryStabilizing;
        break;
      case 'passed':
        stageColor = AeluColors.masteryPassed;
        break;
      case 'seen':
        stageColor = AeluColors.masterySeen;
        break;
      default:
        stageColor = AeluColors.masteryUnseen;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: stageColor,
            ),
          ),
          const SizedBox(width: 12),
          Text(vocab.hanzi, style: HanziStyle.compact),
          const SizedBox(width: 8),
          Text(vocab.pinyin,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: AeluColors.mutedOf(context))),
          const Spacer(),
          Flexible(
            child: Text(
              vocab.english,
              style: theme.textTheme.bodySmall,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.end,
            ),
          ),
        ],
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

class _DetailSkeleton extends StatelessWidget {
  const _DetailSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SkeletonLine(width: 200, height: 28),
          SizedBox(height: 8),
          SkeletonLine(width: 120, height: 20),
          SizedBox(height: 24),
          SkeletonLine(height: 16),
          SizedBox(height: 8),
          SkeletonLine(height: 16),
          SizedBox(height: 8),
          SkeletonLine(width: 250, height: 16),
          SizedBox(height: 32),
          SkeletonLine(width: 80, height: 20),
          SizedBox(height: 12),
          SkeletonPanel(height: 100),
          SizedBox(height: 12),
          SkeletonPanel(height: 100),
        ],
      ),
    );
  }
}
