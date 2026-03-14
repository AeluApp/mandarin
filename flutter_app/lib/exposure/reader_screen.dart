import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/animations/drift_up.dart';
import '../core/error_handler.dart';
import '../core/animations/content_switcher.dart';
import '../core/animations/pressable_scale.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';
import 'widgets/reader_passage.dart';
import 'widgets/word_popup.dart';

class ReaderScreen extends ConsumerStatefulWidget {
  const ReaderScreen({super.key});

  @override
  ConsumerState<ReaderScreen> createState() => _ReaderScreenState();
}

class _ReaderScreenState extends ConsumerState<ReaderScreen> {
  Map<String, dynamic>? _passage;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    ref.read(soundProvider).play(SoundEvent.transitionIn);
    _loadPassage();
  }

  Future<void> _loadPassage() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await ref.read(apiClientProvider).get('/api/reading/passage');
      if (!mounted) return;
      final data = SafeMap.from(response.data);
      if (data == null) {
        if (!mounted) return;
        setState(() {
          _error = 'Couldn\'t load the passage.';
          _loading = false;
        });
        return;
      }
      setState(() {
        _passage = data;
        _loading = false;
      });
    } catch (e, st) {
      ErrorHandler.log('Reader load passage', e, st);
      if (!mounted) return;
      setState(() {
        _error = 'Couldn\'t load the passage.';
        _loading = false;
      });
    }
  }

  Future<void> _lookupWord(String hanzi) async {
    unawaited(HapticFeedback.selectionClick());
    unawaited(ref.read(soundProvider).play(SoundEvent.readingLookup));
    try {
      final response = await ref.read(apiClientProvider).post(
        '/api/reading/lookup',
        data: {'hanzi': hanzi},
      );
      final data = response.data;
      if (!mounted) return;
      if (data is Map<String, dynamic>) {
        unawaited(WordPopup.show(context, data));
      }
    } catch (e, st) {
      ErrorHandler.log('Reader word lookup', e, st);
      // Lookup is best-effort; don't interrupt reading flow.
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Graded Reader'),
        actions: [
          PressableScale(
            onTap: () {
              unawaited(HapticFeedback.lightImpact());
              unawaited(_loadPassage());
            },
            child: Semantics(
              button: true,
              label: 'Refresh passage',
              child: const Padding(
                padding: EdgeInsets.all(10),
                child: Icon(Icons.refresh_outlined, size: 24),
              ),
            ),
          ),
        ],
      ),
      body: ContentSwitcher(
        child: _loading
          ? const _ReaderSkeleton()
          : _error != null
              ? Center(
                  key: const ValueKey('error'),
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.error_outline, size: 56, color: AeluColors.mutedOf(context)),
                        const SizedBox(height: 16),
                        Text(_error!, style: theme.textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Text(
                          'Check your connection and try again.',
                          style: theme.textTheme.bodySmall,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 20),
                        OutlinedButton(onPressed: _loadPassage, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : _passage == null
                  ? Center(
                  key: const ValueKey('empty'),
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.menu_book_outlined, size: 56, color: AeluColors.mutedOf(context)),
                        const SizedBox(height: 16),
                        Text('Stories unlock as you learn', style: theme.textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Text(
                          'Graded passages are written to match your vocabulary. Complete a few sessions and your first story will appear here.',
                          style: theme.textTheme.bodySmall,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 20),
                        OutlinedButton(
                          onPressed: _loadPassage,
                          child: const Text('Check again'),
                        ),
                      ],
                    ),
                  ),
                )
                  : SingleChildScrollView(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (_passage?.strOrNull('title') != null)
                            DriftUp(
                              child: Text(
                                _passage!.str('title'),
                                style: theme.textTheme.headlineLarge,
                              ),
                            ),
                          const SizedBox(height: 8),
                          if (_passage?.strOrNull('level') != null)
                            DriftUp(
                              delay: const Duration(milliseconds: 50),
                              child: Chip(label: Text(_passage!.str('level'))),
                            ),
                          const SizedBox(height: 16),
                          // RichText-based renderer — no per-char widgets.
                          DriftUp(
                            delay: const Duration(milliseconds: 100),
                            child: ReaderPassage(
                              text: _passage?.str('text') ?? '',
                              onWordTap: _lookupWord,
                            ),
                          ),
                        ],
                      ),
                    ),
      ),
    );
  }
}

class _ReaderSkeleton extends StatelessWidget {
  const _ReaderSkeleton();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SkeletonLine(width: 200, height: 24),
          const SizedBox(height: 8),
          const SkeletonLine(width: 60, height: 20),
          const SizedBox(height: 16),
          ...List.generate(6, (_) => const Padding(
            padding: EdgeInsets.only(bottom: 12),
            child: SkeletonLine(height: 22),
          )),
        ],
      ),
    );
  }
}
