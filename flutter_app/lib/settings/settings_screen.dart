import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';
import '../auth/auth_provider.dart';
import '../core/animations/drift_up.dart';
import '../theme/aelu_spacing.dart';
import '../core/animations/pressable_scale.dart';
import '../core/error_handler.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../payments/payment_provider.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../shared/widgets/gesture_tutorial.dart';
import '../theme/aelu_colors.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: [
          // Pro upgrade CTA (hidden if already subscribed)
          _UpgradeBanner(),

          // Account section
          DriftUp(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionHeader(title: 'Account'),
                _SettingsTile(
                  icon: Icons.person_outline,
                  title: 'Profile',
                  onTap: () => context.push('/settings/profile'),
                ),
                _SettingsTile(
                  icon: Icons.security_outlined,
                  title: 'Two-Factor Authentication',
                  onTap: () => context.push('/settings/mfa'),
                ),
                _ChangePasswordTile(),
              ],
            ),
          ),

          const Divider(),

          // Preferences section
          DriftUp(
            delay: const Duration(milliseconds: 80),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionHeader(title: 'Preferences'),
                _SettingsTile(
                  icon: Icons.notifications_outlined,
                  title: 'Notifications',
                  onTap: () => context.push('/settings/notifications'),
                ),
                _SettingsTile(
                  icon: Icons.palette_outlined,
                  title: 'Appearance',
                  onTap: () => context.push('/settings/appearance'),
                ),
                _SettingsTile(
                  icon: Icons.tune_outlined,
                  title: 'Session Preferences',
                  onTap: () => context.push('/settings/session-prefs'),
                ),
                _SettingsTile(
                  icon: Icons.record_voice_over_outlined,
                  title: 'Voice & TTS',
                  onTap: () => context.push('/settings/voice'),
                ),
                _SoundToggle(),
                _GestureTutorialReset(),
              ],
            ),
          ),

          const Divider(),

          // Data section
          DriftUp(
            delay: const Duration(milliseconds: 160),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionHeader(title: 'Data & Privacy'),
                _SettingsTile(
                  icon: Icons.download_outlined,
                  title: 'Export Data',
                  onTap: () => context.push('/settings/gdpr'),
                ),
              ],
            ),
          ),

          const Divider(),

          // About section
          DriftUp(
            delay: const Duration(milliseconds: 240),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionHeader(title: 'About'),
                _SettingsTile(
                  icon: Icons.info_outline,
                  title: 'About Aelu',
                  onTap: () => context.push('/settings/about'),
                ),
              ],
            ),
          ),

          const Divider(),

          // Sign out
          DriftUp(
            delay: const Duration(milliseconds: 320),
            child: Builder(builder: (ctx) {
              final errorColor = Theme.of(ctx).colorScheme.error;
              return PressableScale(
                onTap: () => _confirmSignOut(context, ref),
                child: ListTile(
                  leading: Icon(Icons.logout_outlined, color: errorColor),
                  title: Text('Sign out', style: TextStyle(color: errorColor)),
                ),
              );
            }),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    unawaited(HapticFeedback.selectionClick());
    final confirmed = await showModalBottomSheet<bool>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Handle bar
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: AeluColors.muted.withValues(alpha: 0.3),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              Text(
                'Sign out of Aelu?',
                style: Theme.of(ctx).textTheme.titleLarge,
              ),
              const SizedBox(height: 24),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Cancel'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      child: const Text('Sign Out'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
    if (confirmed == true) {
      unawaited(HapticFeedback.mediumImpact());
      await ref.read(authProvider.notifier).logout();
      if (context.mounted) context.go('/auth/login');
    }
  }
}

class _SettingsTile extends ConsumerWidget {
  final IconData icon;
  final String title;
  final VoidCallback onTap;
  const _SettingsTile({required this.icon, required this.title, required this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return PressableScale(
      onTap: () {
        ref.read(soundProvider).play(SoundEvent.navigate);
        onTap();
      },
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        trailing: const Icon(Icons.chevron_right),
      ),
    );
  }
}

class _SoundToggle extends ConsumerStatefulWidget {
  @override
  ConsumerState<_SoundToggle> createState() => _SoundToggleState();
}

class _SoundToggleState extends ConsumerState<_SoundToggle> {
  late bool _muted;

  @override
  void initState() {
    super.initState();
    _muted = ref.read(soundProvider).muted;
  }

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(_muted ? Icons.volume_off_outlined : Icons.volume_up_outlined),
      title: const Text('Sound Effects'),
      trailing: Switch.adaptive(
        value: !_muted,
        activeTrackColor: AeluColors.accentOf(context),
        onChanged: (enabled) {
          HapticFeedback.selectionClick();
          setState(() => _muted = !enabled);
          ref.read(soundProvider).setMuted(!enabled);
        },
      ),
    );
  }
}

class _ChangePasswordTile extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return PressableScale(
      onTap: () {
        ref.read(soundProvider).play(SoundEvent.navigate);
        _showChangePasswordSheet(context, ref);
      },
      child: const ListTile(
        leading: Icon(Icons.lock_reset_outlined),
        title: Text('Change Password'),
        trailing: Icon(Icons.chevron_right),
      ),
    );
  }

  Future<void> _showChangePasswordSheet(BuildContext context, WidgetRef ref) async {
    unawaited(HapticFeedback.selectionClick());
    final confirmed = await showModalBottomSheet<bool>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: AeluColors.muted.withValues(alpha: 0.3),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              Text(
                'Change Password',
                style: Theme.of(ctx).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              Text(
                'We\'ll send a password reset link to your email address.',
                style: Theme.of(ctx).textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('Send Reset Link'),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () => Navigator.pop(ctx, false),
                  child: const Text('Cancel'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (confirmed == true && context.mounted) {
      try {
        await ref.read(apiClientProvider).post(
          '/api/auth/forgot-password',
          data: {'email': '_current_user_'},
        );
      } catch (e, st) {
        ErrorHandler.log('Settings change password', e, st);
      }
      if (context.mounted) {
        AeluSnackbar.show(
          context,
          'If that email is on file, we sent a reset link.',
          type: SnackbarType.success,
        );
      }
    }
  }
}

class _GestureTutorialReset extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return PressableScale(
      onTap: () async {
        unawaited(HapticFeedback.selectionClick());
        final prefs = await SharedPreferences.getInstance();
        await prefs.remove(GestureTutorial.prefKey);
        if (context.mounted) {
          AeluSnackbar.show(
            context,
            'Gesture hints will appear on your next session.',
            type: SnackbarType.success,
          );
        }
      },
      child: const ListTile(
        leading: Icon(Icons.swipe_outlined),
        title: Text('Show gesture hints again'),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 24, 16, 8),
      child: Text(
        title,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(color: AeluColors.mutedOf(context)),
      ),
    );
  }
}

class _UpgradeBanner extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final payment = ref.watch(paymentProvider);
    if (payment.loading || payment.isActive) return const SizedBox.shrink();

    final theme = Theme.of(context);
    return DriftUp(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
        child: PressableScale(
          onTap: () {
            ref.read(soundProvider).play(SoundEvent.navigate);
            context.push('/settings/subscription');
          },
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  AeluColors.accent.withValues(alpha: 0.08),
                  AeluColors.accent.withValues(alpha: 0.04),
                ],
              ),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AeluColors.accent.withValues(alpha: 0.2)),
            ),
            child: Row(
              children: [
                Icon(Icons.workspace_premium_outlined, color: AeluColors.accentOf(context)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Upgrade to Pro', style: theme.textTheme.titleSmall),
                      Text(
                        'Unlimited sessions, graded reading & more',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: AeluColors.mutedOf(context),
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right, color: AeluColors.mutedOf(context), size: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
