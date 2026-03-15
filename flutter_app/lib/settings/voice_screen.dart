import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:audioplayers/audioplayers.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../config.dart';
import '../core/animations/drift_up.dart';
import '../core/animations/pressable_scale.dart';
import '../core/error_handler.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../theme/aelu_colors.dart';

/// Voice option from the backend.
class _VoiceOption {
  final String key;
  final String label;
  final String description;

  const _VoiceOption({
    required this.key,
    required this.label,
    required this.description,
  });
}

const _voices = [
  _VoiceOption(
    key: 'female',
    label: 'Xiaoxiao',
    description: 'Female, clear and warm',
  ),
  _VoiceOption(
    key: 'male',
    label: 'Yunxi',
    description: 'Male, calm and natural',
  ),
  _VoiceOption(
    key: 'young',
    label: 'Xiaoyi',
    description: 'Young female, bright',
  ),
  _VoiceOption(
    key: 'narrator',
    label: 'Yunjian',
    description: 'Male, authoritative',
  ),
  _VoiceOption(
    key: 'news',
    label: 'Yunyang',
    description: 'Male, news anchor',
  ),
];

class VoiceScreen extends ConsumerStatefulWidget {
  const VoiceScreen({super.key});

  @override
  ConsumerState<VoiceScreen> createState() => _VoiceScreenState();
}

class _VoiceScreenState extends ConsumerState<VoiceScreen> {
  String _selectedVoice = 'female';
  bool _loading = true;
  bool _saving = false;
  final AudioPlayer _player = AudioPlayer();

  @override
  void initState() {
    super.initState();
    _loadCurrentVoice();
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _loadCurrentVoice() async {
    try {
      final response =
          await ref.read(apiClientProvider).get('/api/settings/voice');
      final data = SafeMap.from(response.data);
      if (data != null && mounted) {
        setState(() {
          _selectedVoice = data.str('voice').isNotEmpty
              ? data.str('voice')
              : 'female';
          _loading = false;
        });
      } else if (mounted) {
        setState(() => _loading = false);
      }
    } catch (e, st) {
      ErrorHandler.log('Voice load current', e, st);
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _preview(String voiceKey) async {
    unawaited(HapticFeedback.selectionClick());
    try {
      final text = Uri.encodeQueryComponent('你好，我是你的中文老师。');
      await _player.play(
          UrlSource('${AppConfig.apiUrl}/api/tts?text=$text&voice=$voiceKey'));
    } catch (e, st) {
      ErrorHandler.log('Voice preview', e, st);
    }
  }

  Future<void> _save(String voiceKey) async {
    setState(() {
      _selectedVoice = voiceKey;
      _saving = true;
    });
    try {
      await ref.read(apiClientProvider).post(
        '/api/settings/voice',
        data: {'voice': voiceKey},
      );
      if (mounted) {
        setState(() => _saving = false);
        AeluSnackbar.show(context, 'Voice updated',
            type: SnackbarType.success);
      }
    } catch (e, st) {
      ErrorHandler.log('Voice save', e, st);
      if (mounted) {
        setState(() => _saving = false);
        AeluSnackbar.show(context, 'Couldn\'t save. Try again.',
            type: SnackbarType.error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(title: const Text('Voice & TTS')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                DriftUp(
                  child: Text(
                    'Choose a voice for audio playback. All voices are neural TTS with native Mandarin pronunciation.',
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(color: AeluColors.mutedOf(context)),
                  ),
                ),
                const SizedBox(height: 24),
                ..._voices.asMap().entries.map((entry) {
                  final i = entry.key;
                  final voice = entry.value;
                  final isSelected = _selectedVoice == voice.key;

                  return DriftUp(
                    delay: Duration(milliseconds: 40 + i * 40),
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: PressableScale(
                        onTap: () => _save(voice.key),
                        child: Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: isDark
                                ? AeluColors.surfaceAltDark
                                : AeluColors.surfaceAltLight,
                            borderRadius: BorderRadius.circular(12),
                            border: isSelected
                                ? Border.all(
                                    color: AeluColors.accentOf(context),
                                    width: 2)
                                : null,
                          ),
                          child: Row(
                            children: [
                              Radio<String>(
                                value: voice.key,
                                groupValue: _selectedVoice,
                                activeColor: AeluColors.accentOf(context),
                                onChanged: (v) {
                                  if (v != null) _save(v);
                                },
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.start,
                                  children: [
                                    Text(voice.label,
                                        style: theme.textTheme.titleSmall),
                                    Text(
                                      voice.description,
                                      style: theme.textTheme.bodySmall
                                          ?.copyWith(
                                              color: AeluColors.mutedOf(
                                                  context)),
                                    ),
                                  ],
                                ),
                              ),
                              PressableScale(
                                onTap: () => _preview(voice.key),
                                child: Semantics(
                                  button: true,
                                  label: 'Preview ${voice.label} voice',
                                  child: Container(
                                    width: 40,
                                    height: 40,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: AeluColors.accent
                                          .withValues(alpha: 0.1),
                                    ),
                                    child: Icon(
                                      Icons.play_arrow_rounded,
                                      size: 20,
                                      color: AeluColors.accentOf(context),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                }),
                if (_saving) ...[
                  const SizedBox(height: 16),
                  Center(
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AeluColors.mutedOf(context),
                      ),
                    ),
                  ),
                ],
              ],
            ),
    );
  }
}
