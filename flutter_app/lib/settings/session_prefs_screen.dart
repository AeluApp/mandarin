import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/animations/drift_up.dart';
import '../core/error_handler.dart';
import '../core/animations/content_switcher.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../theme/aelu_colors.dart';

class SessionPrefsScreen extends ConsumerStatefulWidget {
  const SessionPrefsScreen({super.key});

  @override
  ConsumerState<SessionPrefsScreen> createState() => _SessionPrefsScreenState();
}

class _SessionPrefsScreenState extends ConsumerState<SessionPrefsScreen> {
  double _sessionLength = 12;
  bool _loading = true;
  bool _loadError = false;

  @override
  void initState() {
    super.initState();
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    setState(() {
      _loading = true;
      _loadError = false;
    });
    try {
      final response = await ref.read(apiClientProvider).get('/api/account/preferences');
      final data = SafeMap.from(response.data);
      if (data == null) return;
      setState(() {
        _sessionLength = data.integer('session_length', 12).toDouble().clamp(4, 30);
        _loading = false;
      });
    } catch (e, st) {
      ErrorHandler.log('Session prefs load', e, st);
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = true;
      });
    }
  }

  Future<void> _save() async {
    try {
      await ref.read(apiClientProvider).put('/api/account/preferences', data: {
        'session_length': _sessionLength.round(),
      });
      if (mounted) {
        AeluSnackbar.show(context, 'Saved.', type: SnackbarType.success);
      }
    } catch (e, st) {
      ErrorHandler.log('Session prefs save', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t save. Try again.', type: SnackbarType.error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Session Preferences')),
      body: ContentSwitcher(
        child: _loading
          ? const Center(key: ValueKey('loading'), child: CircularProgressIndicator())
          : _loadError
              ? Center(
                  key: const ValueKey('error'),
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.error_outline, size: 56, color: AeluColors.mutedOf(context)),
                        const SizedBox(height: 16),
                        Text('Couldn\'t load preferences',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Text('Check your connection and try again.',
                            style: Theme.of(context).textTheme.bodySmall,
                            textAlign: TextAlign.center),
                        const SizedBox(height: 20),
                        OutlinedButton(onPressed: _loadPrefs, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  DriftUp(
                    child: Text('Session Length', style: theme.textTheme.titleMedium),
                  ),
                  const SizedBox(height: 8),
                  DriftUp(
                    delay: const Duration(milliseconds: 50),
                    child: Text(
                      '${_sessionLength.round()} items per session',
                      style: theme.textTheme.bodyLarge,
                    ),
                  ),
                  const SizedBox(height: 16),
                  DriftUp(
                    delay: const Duration(milliseconds: 100),
                    child: Semantics(
                      label: '${_sessionLength.round()} items',
                      child: Slider(
                      value: _sessionLength,
                      min: 4,
                      max: 30,
                      divisions: 26,
                      label: '${_sessionLength.round()}',
                      activeColor: AeluColors.accentOf(context),
                      onChanged: (v) {
                        HapticFeedback.selectionClick();
                        setState(() => _sessionLength = v);
                      },
                      onChangeEnd: (_) => _save(),
                    ),
                  ),
                  ),
                  DriftUp(
                    delay: const Duration(milliseconds: 150),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('4 (quick)', style: theme.textTheme.bodySmall),
                        Text('30 (deep)', style: theme.textTheme.bodySmall),
                      ],
                    ),
                  ),
                ],
              ),
            ),
      ),
    );
  }
}
