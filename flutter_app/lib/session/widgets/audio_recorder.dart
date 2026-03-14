import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';

import '../../core/sound/aelu_sound.dart';
import '../../core/sound/sound_events.dart';
import '../../shared/widgets/aelu_snackbar.dart';
import '../../theme/aelu_colors.dart';
import '../../core/animations/breathe.dart';

/// Mic recording button with waveform-style visual.
class AudioRecorderWidget extends ConsumerStatefulWidget {
  final ValueChanged<String> onRecorded; // base64 WAV data

  const AudioRecorderWidget({super.key, required this.onRecorded});

  @override
  ConsumerState<AudioRecorderWidget> createState() => _AudioRecorderWidgetState();
}

class _AudioRecorderWidgetState extends ConsumerState<AudioRecorderWidget> {
  final _recorder = AudioRecorder();
  bool _recording = false;
  String? _tempPath;

  Future<void> _toggleRecording() async {
    if (_recording) {
      final path = await _recorder.stop();
      setState(() => _recording = false);
      if (path != null) {
        final file = File(path);
        final bytes = await file.readAsBytes();
        widget.onRecorded(base64Encode(bytes));
        await file.delete();
      }
    } else {
      unawaited(ref.read(soundProvider).play(SoundEvent.recordPulse));
      if (await _recorder.hasPermission()) {
        _tempPath = '${Directory.systemTemp.path}/aelu_recording.wav';
        await _recorder.start(
          const RecordConfig(
            encoder: AudioEncoder.wav,
            numChannels: 1,
            sampleRate: 16000,
          ),
          path: _tempPath!,
        );
        setState(() => _recording = true);
      } else {
        if (mounted) {
          AeluSnackbar.show(
            context,
            'Microphone permission is required for speaking drills.',
            type: SnackbarType.error,
          );
        }
      }
    }
  }

  @override
  void dispose() {
    _recorder.dispose();
    // Clean up temp recording file if it exists.
    if (_tempPath != null) {
      final file = File(_tempPath!);
      if (file.existsSync()) {
        file.deleteSync();
      }
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final icon = _recording ? Icons.stop_outlined : Icons.mic_outlined;
    final label = _recording ? 'Stop recording' : 'Start recording';

    final button = Semantics(
      button: true,
      label: label,
      child: SizedBox(
        width: 72,
        height: 72,
        child: ElevatedButton(
          onPressed: _toggleRecording,
          style: ElevatedButton.styleFrom(
            shape: const CircleBorder(),
            padding: EdgeInsets.zero,
            backgroundColor: _recording ? AeluColors.incorrect : AeluColors.accent,
          ),
          child: Icon(icon, size: 32, color: AeluColors.onAccent),
        ),
      ),
    );

    return Center(
      child: _recording ? Breathe(child: button) : button,
    );
  }
}
