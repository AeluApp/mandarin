import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/animations/drift_up.dart';
import '../core/error_handler.dart';
import '../core/security/security_config.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../core/animations/content_switcher.dart';
import '../shared/widgets/skeleton.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    try {
      final response = await ref.read(apiClientProvider).get('/api/account/profile');
      if (!mounted) return;
      final data = SafeMap.from(response.data);
      if (data == null) return;
      _nameController.text = data.str('display_name');
      _emailController.text = data.str('email');
      setState(() => _loading = false);
    } catch (e, st) {
      ErrorHandler.log('Profile load', e, st);
      if (!mounted) return;
      setState(() => _loading = false);
      AeluSnackbar.show(context, 'Couldn\'t load your profile.', type: SnackbarType.error);
    }
  }

  Future<void> _save() async {
    unawaited(HapticFeedback.selectionClick());
    final displayName = InputSanitizer.sanitize(_nameController.text);
    final email = InputSanitizer.sanitize(_emailController.text);
    if (displayName.isEmpty) {
      AeluSnackbar.show(context, 'You\'ll need a display name to save.', type: SnackbarType.error);
      return;
    }
    if (!InputSanitizer.isValidEmail(email)) {
      AeluSnackbar.show(context, 'That doesn\'t look like an email address.', type: SnackbarType.error);
      return;
    }
    setState(() => _saving = true);
    try {
      await ref.read(apiClientProvider).put('/api/account/profile', data: {
        'display_name': displayName,
        'email': email,
      });
      if (mounted) {
        AeluSnackbar.show(context, 'Changes saved.', type: SnackbarType.success);
      }
    } catch (e, st) {
      ErrorHandler.log('Profile save', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t save your changes. Try again.', type: SnackbarType.error);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ContentSwitcher(
        child: _loading
          ? const Padding(
              key: ValueKey('loading'),
              padding: EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SkeletonLine(width: 200, height: 20),
                  SizedBox(height: 24),
                  SkeletonLine(height: 48),
                  SizedBox(height: 16),
                  SkeletonLine(height: 48),
                  SizedBox(height: 24),
                  SkeletonLine(height: 44),
                ],
              ),
            )
          : SingleChildScrollView(
              key: const ValueKey('content'),
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  DriftUp(
                    child: TextField(
                      controller: _nameController,
                      decoration: const InputDecoration(
                        labelText: 'Display name',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                      textInputAction: TextInputAction.next,
                    ),
                  ),
                  const SizedBox(height: 16),
                  DriftUp(
                    delay: const Duration(milliseconds: 50),
                    child: TextField(
                      controller: _emailController,
                      decoration: const InputDecoration(
                        labelText: 'Email',
                        prefixIcon: Icon(Icons.email_outlined),
                      ),
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.done,
                      onSubmitted: (_) => _save(),
                    ),
                  ),
                  const SizedBox(height: 24),
                  DriftUp(
                    delay: const Duration(milliseconds: 100),
                    child: SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: _saving ? null : _save,
                        child: _saving
                            ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                            : const Text('Save'),
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
