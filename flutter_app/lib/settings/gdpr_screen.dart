import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_client.dart';
import '../core/animations/drift_up.dart';
import '../core/error_handler.dart';
import '../auth/auth_provider.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../theme/aelu_colors.dart';

class GdprScreen extends ConsumerStatefulWidget {
  const GdprScreen({super.key});

  @override
  ConsumerState<GdprScreen> createState() => _GdprScreenState();
}

class _GdprScreenState extends ConsumerState<GdprScreen> {
  bool _exporting = false;
  bool _deleting = false;

  Future<void> _exportData() async {
    unawaited(HapticFeedback.selectionClick());
    setState(() => _exporting = true);
    try {
      await ref.read(apiClientProvider).get('/api/account/export');
      if (mounted) {
        AeluSnackbar.show(context, 'Your export is on its way — check your email.', type: SnackbarType.success);
      }
    } catch (e, st) {
      ErrorHandler.log('GDPR export data', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t start the export. Try again.', type: SnackbarType.error);
      }
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _confirmDelete() async {
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
              Icon(Icons.warning_amber_outlined, size: 40, color: Theme.of(ctx).colorScheme.error),
              const SizedBox(height: 16),
              Text(
                'Delete Account?',
                style: Theme.of(ctx).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                'This will permanently delete your account and all learning data. This cannot be undone.',
                style: Theme.of(ctx).textTheme.bodyMedium,
                textAlign: TextAlign.center,
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
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AeluColors.incorrect,
                      ),
                      child: const Text('Delete'),
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
      setState(() => _deleting = true);
      try {
        await ref.read(apiClientProvider).post('/api/account/delete');
        await ref.read(authProvider.notifier).logout();
        if (mounted) context.go('/auth/login');
      } catch (e, st) {
        ErrorHandler.log('GDPR delete account', e, st);
        if (mounted) {
          AeluSnackbar.show(context, 'Couldn\'t delete your account. Reach out to support and we\'ll help.', type: SnackbarType.error);
          setState(() => _deleting = false);
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Data & Privacy')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          DriftUp(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Export Data', style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                Text(
                  'Download all your learning data, session history, and preferences.',
                  style: theme.textTheme.bodyMedium,
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: _exporting ? null : _exportData,
                    icon: _exporting
                        ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.download_outlined),
                    label: Text(_exporting ? 'Exporting...' : 'Export My Data'),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 40),
          DriftUp(
            delay: const Duration(milliseconds: 150),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Delete Account', style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                Text(
                  'Permanently delete your account and all associated data. This cannot be undone.',
                  style: theme.textTheme.bodyMedium,
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
              onPressed: _deleting ? null : _confirmDelete,
              icon: _deleting
                  ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : Icon(Icons.delete_outline, color: Theme.of(context).colorScheme.error),
              label: Text(
                _deleting ? 'Deleting...' : 'Delete Account',
                style: _deleting ? null : TextStyle(color: Theme.of(context).colorScheme.error),
              ),
              style: OutlinedButton.styleFrom(
                side: BorderSide(color: Theme.of(context).colorScheme.error),
              ),
            ),
          ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
