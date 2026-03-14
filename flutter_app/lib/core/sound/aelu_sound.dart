import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../error_handler.dart';
import 'sound_events.dart';

/// Physical-modeled sound engine.
///
/// Pre-rendered WAV files bundled as assets, played via audioplayers.
/// Each event also triggers platform haptics.
///
/// Performance:
/// - Pre-warm players load in parallel (not sequential).
/// - Player pool is capped to prevent unbounded accumulation.
class AeluSound {
  final Map<SoundEvent, AudioPlayer> _players = {};
  bool _muted = false;

  static const _maxPlayers = 16;
  static const _muteKey = 'aelu_sound_muted';

  bool get muted => _muted;

  Future<void> init() async {
    // Restore persisted mute state.
    try {
      final prefs = await SharedPreferences.getInstance();
      _muted = prefs.getBool(_muteKey) ?? false;
    } catch (e, st) {
      ErrorHandler.log('Sound load mute pref', e, st);
    }

    // Configure audio session: ambient category mixes with other audio
    // and respects the device silent switch on iOS.
    try {
      final ctx = AudioContext(
        iOS: AudioContextIOS(
          category: AVAudioSessionCategory.ambient,
          options: const {},
        ),
        android: const AudioContextAndroid(
          usageType: AndroidUsageType.assistanceSonification,
          contentType: AndroidContentType.sonification,
        ),
      );
      await AudioPlayer.global.setAudioContext(ctx);
    } catch (e, st) {
      ErrorHandler.log('Sound set audio context', e, st);
    }

    // Pre-warm players for latency-critical events — parallel load.
    final warmEvents = [
      SoundEvent.correct,
      SoundEvent.wrong,
      SoundEvent.navigate,
      SoundEvent.sessionStart,
    ];

    await Future.wait(
      warmEvents.map((event) async {
        try {
          final player = AudioPlayer();
          await player.setSource(AssetSource('sounds/${event.assetName}.wav'));
          await player.setReleaseMode(ReleaseMode.stop);
          _players[event] = player;
        } catch (e, st) {
          ErrorHandler.log('Sound pre-warm ${event.assetName}', e, st);
          // Non-fatal — haptic-only fallback for this event.
        }
      }),
      eagerError: false,
    );
  }

  /// Toggle mute state and persist to SharedPreferences.
  Future<void> setMuted(bool value) async {
    _muted = value;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_muteKey, value);
    } catch (e, st) {
      ErrorHandler.log('Sound save mute pref', e, st);
    }
  }

  /// Play a sound event with associated haptic feedback.
  Future<void> play(SoundEvent event) async {
    _triggerHaptic(event.haptic);

    if (_muted) return;

    var player = _players[event];
    if (player != null) {
      await player.seek(Duration.zero);
      await player.resume();
    } else {
      // Evict oldest player if pool is at capacity.
      if (_players.length >= _maxPlayers) {
        final oldest = _players.keys.first;
        final evicted = _players.remove(oldest);
        if (evicted != null) unawaited(evicted.dispose());
      }

      player = AudioPlayer();
      try {
        await player.play(AssetSource('sounds/${event.assetName}.wav'));
        _players[event] = player;
      } catch (e, st) {
        ErrorHandler.log('Sound play asset', e, st);
        unawaited(player.dispose());
        // Asset missing — haptic-only fallback.
      }
    }
  }

  void _triggerHaptic(HapticType type) {
    switch (type) {
      case HapticType.none:
        break;
      case HapticType.selection:
        unawaited(HapticFeedback.selectionClick());
        break;
      case HapticType.light:
        unawaited(HapticFeedback.lightImpact());
        break;
      case HapticType.medium:
        unawaited(HapticFeedback.mediumImpact());
        break;
      case HapticType.heavy:
        unawaited(HapticFeedback.heavyImpact());
        break;
    }
  }

  void dispose() {
    for (final player in _players.values) {
      player.dispose();
    }
    _players.clear();
  }
}

final soundProvider = Provider<AeluSound>((ref) {
  final sound = AeluSound();
  ref.onDispose(() => sound.dispose());
  return sound;
});
