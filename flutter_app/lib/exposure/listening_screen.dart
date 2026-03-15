import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:audioplayers/audioplayers.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../config.dart';
import '../core/error_handler.dart';
import '../core/animations/content_switcher.dart';
import '../core/animations/drift_up.dart';
import '../core/animations/pressable_scale.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';
import 'widgets/audio_progress.dart';
import 'widgets/speed_control.dart';

class ListeningScreen extends ConsumerStatefulWidget {
  const ListeningScreen({super.key});

  @override
  ConsumerState<ListeningScreen> createState() => _ListeningScreenState();
}

class _ListeningScreenState extends ConsumerState<ListeningScreen> {
  Map<String, dynamic>? _passage;
  bool _loading = true;
  bool _loadError = false;
  bool _playing = false;
  bool _showTranscript = false;
  double _speed = 1.0;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  final AudioPlayer _player = AudioPlayer();
  StreamSubscription? _positionSub;
  StreamSubscription? _durationSub;
  StreamSubscription? _completeSub;

  @override
  void initState() {
    super.initState();
    ref.read(soundProvider).play(SoundEvent.transitionIn);
    _player.setAudioContext(AudioContext(
      iOS: AudioContextIOS(
        category: AVAudioSessionCategory.playback,
        options: const {},
      ),
      android: const AudioContextAndroid(
        usageType: AndroidUsageType.media,
        contentType: AndroidContentType.speech,
      ),
    ));
    _positionSub = _player.onPositionChanged.listen((p) {
      if (mounted) setState(() => _position = p);
    });
    _durationSub = _player.onDurationChanged.listen((d) {
      if (mounted) setState(() => _duration = d);
    });
    _completeSub = _player.onPlayerComplete.listen((_) {
      if (mounted) setState(() => _playing = false);
    });
    _loadPassage();
  }

  Future<void> _loadPassage() async {
    setState(() {
      _loading = true;
      _loadError = false;
    });
    try {
      final response =
          await ref.read(apiClientProvider).get('/api/listening/passage');
      if (!mounted) return;
      final data = SafeMap.from(response.data);
      if (data == null) return;
      setState(() {
        _passage = data;
        _loading = false;
        _playing = false;
        _position = Duration.zero;
        _duration = Duration.zero;
      });
    } catch (e, st) {
      ErrorHandler.log('Listening load passage', e, st);
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = true;
      });
    }
  }

  Future<void> _togglePlay() async {
    unawaited(HapticFeedback.lightImpact());
    if (_playing) {
      await _player.pause();
      if (mounted) setState(() => _playing = false);
    } else {
      final audioUrl = _passage?.strOrNull('audio_url');
      if (audioUrl != null) {
        // SECURITY: Validate audio URL is a relative API path.
        if (!audioUrl.startsWith('/api/')) return;
        if (_position > Duration.zero) {
          await _player.resume();
        } else {
          await _player.play(UrlSource('${AppConfig.apiUrl}$audioUrl'));
        }
        await _player.setPlaybackRate(_speed);
        if (mounted) setState(() => _playing = true);
      }
    }
  }

  Future<void> _seek(Duration position) async {
    await _player.seek(position);
  }

  Future<void> _setSpeed(double speed) async {
    setState(() => _speed = speed);
    await _player.setPlaybackRate(speed);
  }

  Future<void> _markComplete() async {
    unawaited(ref.read(soundProvider).play(SoundEvent.sessionComplete));
    final id = _passage?['id'];
    if (id == null) return;
    try {
      await ref
          .read(apiClientProvider)
          .post('/api/listening/complete', data: {'id': id});
      await _player.stop();
      unawaited(_loadPassage());
    } catch (e, st) {
      ErrorHandler.log('Listening mark complete', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t mark as complete. Try again.', type: SnackbarType.error);
      }
    }
  }

  @override
  void dispose() {
    _positionSub?.cancel();
    _durationSub?.cancel();
    _completeSub?.cancel();
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Listening Practice')),
      body: ContentSwitcher(
        child: _loading
          ? const Center(key: ValueKey('loading'), child: SkeletonPanel(height: 200))
          : _loadError
              ? _ErrorRetry(onRetry: _loadPassage)
              : _passage == null
                  ? const _EmptyState()
                  : SingleChildScrollView(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        children: [
                          if (_passage?.strOrNull('title') != null)
                            DriftUp(
                              child: Text(
                                _passage!.str('title'),
                                style: theme.textTheme.headlineLarge,
                                textAlign: TextAlign.center,
                              ),
                            ),
                          if (_passage?.strOrNull('level') != null) ...[
                            const SizedBox(height: 8),
                            Chip(label: Text(_passage!.str('level'))),
                          ],
                          const SizedBox(height: 40),

                          // Play button — alive
                          DriftUp(
                            delay: const Duration(milliseconds: 100),
                            child: PressableScale(
                              onTap: _togglePlay,
                              child: Semantics(
                                button: true,
                                label: _playing ? 'Pause' : 'Play',
                                child: Container(
                                  width: 80,
                                  height: 80,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: AeluColors.accent,
                                    boxShadow: [
                                      BoxShadow(
                                        color:
                                            AeluColors.accent.withValues(alpha: 0.25),
                                        blurRadius: 16,
                                        offset: const Offset(0, 4),
                                      ),
                                    ],
                                  ),
                                  child: Icon(
                                    _playing
                                        ? Icons.pause_rounded
                                        : Icons.play_arrow_rounded,
                                    size: 40,
                                    color: AeluColors.onAccent,
                                  ),
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 20),

                          // Progress bar
                          AudioProgress(
                            position: _position,
                            duration: _duration,
                            onSeek: _seek,
                          ),
                          const SizedBox(height: 16),

                          // Speed control
                          SpeedControl(
                              speed: _speed, onChanged: _setSpeed),
                          const SizedBox(height: 28),

                          // Transcript toggle
                          PressableScale(
                            onTap: () {
                              ref.read(soundProvider).play(SoundEvent.hintReveal);
                              setState(() => _showTranscript = !_showTranscript);
                            },
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  _showTranscript
                                      ? Icons.visibility_off_outlined
                                      : Icons.visibility_outlined,
                                  size: 16,
                                  color: AeluColors.mutedOf(context),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  _showTranscript
                                      ? 'Hide Transcript'
                                      : 'Show Transcript',
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    color: AeluColors.accentOf(context),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          if (_showTranscript &&
                              _passage?.strOrNull('text') != null) ...[
                            const SizedBox(height: 16),
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: theme.brightness == Brightness.dark
                                    ? AeluColors.surfaceAltDark
                                    : AeluColors.surfaceAltLight,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                _passage!.str('text'),
                                style: theme.textTheme.bodyLarge
                                    ?.copyWith(fontSize: 18, height: 1.8),
                              ),
                            ),
                          ],

                          const SizedBox(height: 28),

                          SizedBox(
                            width: double.infinity,
                            child: PressableScale(
                              onTap: _markComplete,
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 16),
                                decoration: BoxDecoration(
                                  color: AeluColors.accent,
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Text(
                                  'Mark Complete',
                                  style: theme.textTheme.titleMedium?.copyWith(color: AeluColors.onAccent),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
      ),
    );
  }
}

class _ErrorRetry extends StatelessWidget {
  final VoidCallback onRetry;
  const _ErrorRetry({required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 56, color: AeluColors.mutedOf(context)),
            const SizedBox(height: 16),
            Text('Couldn\'t load the passage', style: theme.textTheme.titleMedium),
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

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.headphones_outlined,
                size: 56, color: AeluColors.mutedOf(context)),
            const SizedBox(height: 16),
            Text('Listening unlocks as you learn',
                style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              'Native-speed audio passages are matched to your level. Keep practicing and your first one will appear here.',
              style: theme.textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
