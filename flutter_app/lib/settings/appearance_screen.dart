import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/animations/drift_up.dart';
import '../core/theme_controller.dart';

class AppearanceScreen extends ConsumerWidget {
  const AppearanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(themeControllerProvider);
    final controller = ref.read(themeControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Appearance')),
      body: ListView(
        children: [
          const SizedBox(height: 16),
          DriftUp(
            child: RadioListTile<ThemePreference>(
              title: const Text('Auto (dark 8pm-6am)'),
              subtitle: const Text('Follows time of day'),
              value: ThemePreference.auto,
              // ignore: deprecated_member_use
              groupValue: controller.preference,
              // ignore: deprecated_member_use
              onChanged: (v) {
                HapticFeedback.selectionClick();
                controller.setPreference(v!);
              },
            ),
          ),
          DriftUp(
            delay: const Duration(milliseconds: 50),
            child: RadioListTile<ThemePreference>(
              title: const Text('Light'),
              value: ThemePreference.light,
              // ignore: deprecated_member_use
              groupValue: controller.preference,
              // ignore: deprecated_member_use
              onChanged: (v) {
                HapticFeedback.selectionClick();
                controller.setPreference(v!);
              },
            ),
          ),
          DriftUp(
            delay: const Duration(milliseconds: 100),
            child: RadioListTile<ThemePreference>(
              title: const Text('Dark'),
              value: ThemePreference.dark,
              // ignore: deprecated_member_use
              groupValue: controller.preference,
              // ignore: deprecated_member_use
              onChanged: (v) {
                HapticFeedback.selectionClick();
                controller.setPreference(v!);
              },
            ),
          ),
        ],
      ),
    );
  }
}
