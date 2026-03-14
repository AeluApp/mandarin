import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/animations/content_switcher.dart';
import '../core/error_handler.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../theme/aelu_colors.dart';
import '../shared/widgets/skeleton.dart';
import 'widgets/media_card.dart';

class MediaScreen extends ConsumerStatefulWidget {
  const MediaScreen({super.key});

  @override
  ConsumerState<MediaScreen> createState() => _MediaScreenState();
}

class _MediaScreenState extends ConsumerState<MediaScreen> {
  List<Map<String, dynamic>> _recommendations = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    ref.read(soundProvider).play(SoundEvent.transitionIn);
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await ref.read(apiClientProvider).get('/api/media/recommendations');
      if (!mounted) return;
      final data = SafeMap.from(response.data);
      if (data == null) {
        if (!mounted) return;
        setState(() {
          _error = 'Couldn\'t load recommendations.';
          _loading = false;
        });
        return;
      }
      setState(() {
        _recommendations = data.list('items')
            .whereType<Map<String, dynamic>>()
            .toList();
        _loading = false;
      });
    } catch (e, st) {
      ErrorHandler.log('Media load recommendations', e, st);
      if (!mounted) return;
      setState(() {
        _error = 'Couldn\'t load recommendations.';
        _loading = false;
      });
    }
  }

  Future<void> _markWatched(int id) async {
    unawaited(ref.read(soundProvider).play(SoundEvent.navigate));
    try {
      await ref.read(apiClientProvider).post('/api/media/watched', data: {'id': id});
      unawaited(_load());
    } catch (e, st) {
      ErrorHandler.log('Media mark watched', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t save. Try again.', type: SnackbarType.error);
      }
    }
  }

  Future<void> _skip(int id) async {
    unawaited(ref.read(soundProvider).play(SoundEvent.navigate));
    try {
      await ref.read(apiClientProvider).post('/api/media/skip', data: {'id': id});
      unawaited(_load());
    } catch (e, st) {
      ErrorHandler.log('Media skip item', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t skip. Try again.', type: SnackbarType.error);
      }
    }
  }

  Future<void> _like(int id) async {
    unawaited(ref.read(soundProvider).play(SoundEvent.navigate));
    try {
      await ref.read(apiClientProvider).post('/api/media/liked', data: {'id': id});
    } catch (e, st) {
      ErrorHandler.log('Media save like', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t save. Try again.', type: SnackbarType.error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Media Shelf')),
      body: ContentSwitcher(
        child: _loading
          ? ListView(
              key: const ValueKey('loading'),
              padding: const EdgeInsets.all(16),
              children: List.generate(3, (_) => const Padding(
                padding: EdgeInsets.only(bottom: 8),
                child: SkeletonPanel(height: 100),
              )),
            )
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
                        OutlinedButton(onPressed: _load, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : _recommendations.isEmpty
                  ? Center(
                      key: const ValueKey('empty'),
                      child: Padding(
                        padding: const EdgeInsets.all(32),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.movie_outlined, size: 56, color: AeluColors.mutedOf(context)),
                            const SizedBox(height: 16),
                            Text('Your media shelf is empty', style: theme.textTheme.titleMedium),
                            const SizedBox(height: 8),
                            Text(
                              'Complete a few practice sessions and Aelu will recommend shows, videos, and podcasts matched to your level.',
                              style: theme.textTheme.bodySmall,
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 20),
                            OutlinedButton(
                              onPressed: _load,
                              child: const Text('Check again'),
                            ),
                          ],
                        ),
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: () async => _load(),
                      child: ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _recommendations.length,
                        itemBuilder: (context, index) {
                          final item = _recommendations[index];
                          final id = item['id'] as int? ?? 0;
                          return MediaCard(
                            item: item,
                            onWatched: () => _markWatched(id),
                            onSkip: () => _skip(id),
                            onLike: () => _like(id),
                          );
                        },
                      ),
                    ),
      ),
    );
  }
}
