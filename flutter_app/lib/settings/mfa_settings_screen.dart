import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/animations/drift_up.dart';
import '../core/error_handler.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../core/animations/content_switcher.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';

class MfaSettingsScreen extends ConsumerStatefulWidget {
  const MfaSettingsScreen({super.key});

  @override
  ConsumerState<MfaSettingsScreen> createState() => _MfaSettingsScreenState();
}

class _MfaSettingsScreenState extends ConsumerState<MfaSettingsScreen> {
  bool _enabled = false;
  String? _secret;
  List<String> _backupCodes = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  Future<void> _loadStatus() async {
    try {
      final response = await ref.read(apiClientProvider).get('/api/account/mfa');
      if (!mounted) return;
      final data = SafeMap.from(response.data);
      if (data == null) return;
      setState(() {
        _enabled = data.boolean('enabled');
        _loading = false;
      });
    } catch (e, st) {
      ErrorHandler.log('MFA load status', e, st);
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  Future<void> _enableMfa() async {
    try {
      final response = await ref.read(apiClientProvider).post('/api/account/mfa/enable');
      if (!mounted) return;
      final data = SafeMap.from(response.data);
      if (data == null) return;
      setState(() {
        _secret = data.strOrNull('secret');
        _backupCodes = data.list('backup_codes')
                .map((e) => e.toString())
                .toList();
        _enabled = true;
      });
    } catch (e, st) {
      ErrorHandler.log('MFA enable', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t enable two-factor authentication.', type: SnackbarType.error);
      }
    }
  }

  Future<void> _confirmDisableMfa() async {
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
              Icon(Icons.warning_amber_outlined,
                  color: Theme.of(ctx).colorScheme.error, size: 40),
              const SizedBox(height: 12),
              Text(
                'Disable Two-Factor Auth?',
                style: Theme.of(ctx).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                'This makes your account less secure. You can re-enable it at any time.',
                style: Theme.of(ctx).textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Keep Enabled'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AeluColors.incorrect,
                      ),
                      child: const Text('Disable'),
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
      await _disableMfa();
    }
  }

  Future<void> _disableMfa() async {
    try {
      await ref.read(apiClientProvider).post('/api/account/mfa/disable');
      if (!mounted) return;
      setState(() {
        _enabled = false;
        _secret = null;
        _backupCodes = [];
      });
    } catch (e, st) {
      ErrorHandler.log('MFA disable', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t disable two-factor authentication.', type: SnackbarType.error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Two-Factor Authentication')),
      body: ContentSwitcher(
        child: _loading
          ? const Padding(
              key: ValueKey('loading'),
              padding: EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SkeletonLine(width: 280, height: 48),
                  SizedBox(height: 24),
                  SkeletonLine(width: 160, height: 20),
                  SizedBox(height: 8),
                  SkeletonLine(height: 44),
                ],
              ),
            )
          : SingleChildScrollView(
              key: const ValueKey('content'),
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  DriftUp(
                    child: SwitchListTile(
                    title: const Text('Two-Factor Authentication'),
                    subtitle: Text(_enabled ? 'Enabled' : 'Disabled'),
                    value: _enabled,
                    onChanged: (v) {
                      HapticFeedback.selectionClick();
                      if (v) {
                        _enableMfa();
                      } else {
                        _confirmDisableMfa();
                      }
                    },
                  ),
                  ),
                  if (_secret != null) ...[
                    const SizedBox(height: 24),
                    DriftUp(
                      delay: const Duration(milliseconds: 100),
                      child: Text('Setup Key', style: theme.textTheme.titleMedium),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: SelectableText(
                            _secret!,
                            style: theme.textTheme.bodyLarge?.copyWith(
                              fontFamily: 'monospace',
                            ),
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.content_copy_outlined),
                          tooltip: 'Copy',
                          onPressed: () {
                            Clipboard.setData(ClipboardData(text: _secret!));
                            AeluSnackbar.show(context, 'Copied.', type: SnackbarType.info);
                          },
                        ),
                      ],
                    ),
                  ],
                  if (_backupCodes.isNotEmpty) ...[
                    const SizedBox(height: 24),
                    Row(
                      children: [
                        Expanded(
                          child: Text('Backup Codes', style: theme.textTheme.titleMedium),
                        ),
                        IconButton(
                          icon: const Icon(Icons.content_copy_outlined, size: 20),
                          tooltip: 'Copy all codes',
                          onPressed: () {
                            HapticFeedback.selectionClick();
                            Clipboard.setData(
                              ClipboardData(text: _backupCodes.join('\n')),
                            );
                            AeluSnackbar.show(
                              context,
                              'Backup codes copied.',
                              type: SnackbarType.info,
                            );
                          },
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Save these codes in a safe place. Each can be used once.',
                      style: theme.textTheme.bodySmall,
                    ),
                    const SizedBox(height: 8),
                    ..._backupCodes.map((code) => Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Text(code, style: const TextStyle(fontFamily: 'monospace')),
                    )),
                  ],
                ],
              ),
            ),
      ),
    );
  }
}
