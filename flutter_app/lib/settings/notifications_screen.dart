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

class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  bool _pushEnabled = true;
  bool _streakReminders = true;
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
      final response = await ref.read(apiClientProvider).get('/api/account/notifications');
      final data = SafeMap.from(response.data);
      if (data == null) return;
      setState(() {
        _pushEnabled = data.boolean('push_enabled', true);
        _streakReminders = data.boolean('streak_reminders', true);
        _loading = false;
      });
    } catch (e, st) {
      ErrorHandler.log('Notifications load prefs', e, st);
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = true;
      });
    }
  }

  Future<void> _savePrefs() async {
    try {
      await ref.read(apiClientProvider).put('/api/account/notifications', data: {
        'push_enabled': _pushEnabled,
        'streak_reminders': _streakReminders,
      });
      if (mounted) {
        AeluSnackbar.show(context, 'Saved.', type: SnackbarType.success);
      }
    } catch (e, st) {
      ErrorHandler.log('Notifications save prefs', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t save. Try again.', type: SnackbarType.error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
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
              : ListView(
              children: [
                DriftUp(
                  child: SwitchListTile(
                    title: const Text('Push Notifications'),
                    subtitle: const Text('Session reminders and updates'),
                    value: _pushEnabled,
                    onChanged: (v) {
                      HapticFeedback.selectionClick();
                      setState(() => _pushEnabled = v);
                      _savePrefs();
                    },
                  ),
                ),
                DriftUp(
                  delay: const Duration(milliseconds: 50),
                  child: SwitchListTile(
                    title: const Text('Streak Reminders'),
                    subtitle: const Text('Daily reminder to maintain your streak'),
                    value: _streakReminders,
                    onChanged: (v) {
                      HapticFeedback.selectionClick();
                      setState(() => _streakReminders = v);
                      _savePrefs();
                    },
                  ),
                ),
              ],
            ),
      ),
    );
  }
}
