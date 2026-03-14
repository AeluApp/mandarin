import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_client.dart';
import '../core/error_handler.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../theme/aelu_colors.dart';
import '../theme/aelu_spacing.dart';
import '../core/animations/drift_up.dart';
import '../core/security/security_config.dart';
import 'auth_provider.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _passwordFocusNode = FocusNode();
  bool _loading = false;
  bool _obscurePassword = true;
  String? _error;

  // SECURITY: Client-side rate limiting (OWASP M4, CIS 3.2).
  final _rateLimiter = RateLimiter(
    maxAttempts: SecurityConfig.maxLoginAttempts,
  );

  @override
  void initState() {
    super.initState();
    // SECURITY: Prevent screenshots on auth screen (OWASP M9).
    ScreenshotGuard.enable();

    // Show session expired message if redirected here after timeout.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final auth = ref.read(authProvider);
      if (auth.sessionExpired) {
        ref.read(authProvider.notifier).clearSessionExpired();
        AeluSnackbar.show(
          context,
          'Your session expired. Sign in again to continue.',
          type: SnackbarType.info,
        );
      }
    });
  }

  @override
  void dispose() {
    // SECURITY: Clear sensitive data from controllers.
    _emailController.clear();
    _passwordController.clear();
    _emailController.dispose();
    _passwordController.dispose();
    _passwordFocusNode.dispose();
    ScreenshotGuard.disable();
    super.dispose();
  }

  Future<void> _submit() async {
    // SECURITY: Check rate limiter before attempt.
    if (_rateLimiter.isLockedOut) {
      final remaining = _rateLimiter.remainingLockout;
      setState(() => _error =
          'Too many attempts. Try again in ${remaining?.inSeconds ?? 30}s.');
      return;
    }

    // SECURITY: Sanitize inputs.
    final email = InputSanitizer.sanitize(
        _emailController.text, maxLength: SecurityConfig.maxEmailLength);
    final password = _passwordController.text;

    if (!InputSanitizer.isValidEmail(email)) {
      setState(() => _error = 'That doesn\'t look like an email address.');
      return;
    }
    if (password.isEmpty || password.length > SecurityConfig.maxPasswordLength) {
      setState(() => _error = 'Enter your password to continue.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      await ref.read(authProvider.notifier).login(email, password);

      // SECURITY: Rate limiter — record success.
      _rateLimiter.recordSuccess();

      if (!mounted) return;
      unawaited(ref.read(soundProvider).play(SoundEvent.navigate));
      final auth = ref.read(authProvider);
      if (auth.needsMfa) {
        context.go('/auth/mfa');
      }
    } catch (e, st) {
      ErrorHandler.log('Login submit', e, st);
      // SECURITY: Rate limiter — record failure.
      final lockedOut = _rateLimiter.recordFailure();

      // SECURITY: Generic error message — don't reveal whether email exists.
      if (lockedOut) {
        final remaining = _rateLimiter.remainingLockout;
        setState(() => _error =
            'Too many attempts. Try again in ${remaining?.inSeconds ?? 30}s.');
      } else {
        final remaining = _rateLimiter.remainingAttempts;
        setState(() => _error =
            'Invalid email or password. $remaining attempt${remaining == 1 ? '' : 's'} remaining.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _showForgotPasswordSheet() {
    HapticFeedback.lightImpact();
    final forgotEmailController = TextEditingController(text: _emailController.text.trim());
    bool sending = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheetState) => Padding(
          padding: EdgeInsets.fromLTRB(
            24, 24, 24,
            MediaQuery.of(ctx).viewInsets.bottom + 24,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
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
              Text('Reset Password', style: Theme.of(ctx).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(
                'Enter your email and we\'ll send you a reset link.',
                style: Theme.of(ctx).textTheme.bodyMedium,
              ),
              const SizedBox(height: 16),
              TextField(
                controller: forgotEmailController,
                decoration: const InputDecoration(
                  labelText: 'Email',
                  prefixIcon: Icon(Icons.email_outlined),
                ),
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.done,
                autofillHints: const [AutofillHints.email],
                onSubmitted: (_) async {
                  if (sending) return;
                  setSheetState(() => sending = true);
                  await _sendResetLink(forgotEmailController.text.trim());
                  if (ctx.mounted) Navigator.pop(ctx);
                },
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: sending
                      ? null
                      : () async {
                          setSheetState(() => sending = true);
                          await _sendResetLink(forgotEmailController.text.trim());
                          if (ctx.mounted) Navigator.pop(ctx);
                        },
                  child: sending
                      ? const SizedBox(
                          height: 20, width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Send Reset Link'),
                ),
              ),
            ],
          ),
        ),
      ),
    ).then((_) => forgotEmailController.dispose());
  }

  Future<void> _sendResetLink(String email) async {
    if (!InputSanitizer.isValidEmail(email)) {
      if (mounted) {
        AeluSnackbar.show(context, 'That doesn\'t look like an email address.', type: SnackbarType.error);
      }
      return;
    }
    try {
      await ref.read(apiClientProvider).post(
        '/api/auth/forgot-password',
        data: {'email': InputSanitizer.sanitize(email)},
      );
    } catch (e, st) {
      ErrorHandler.log('Login send reset link', e, st);
      // Intentionally silent — don't reveal if email exists.
    }
    if (mounted) {
      AeluSnackbar.show(
        context,
        'If that email is on file, we sent a reset link.',
        type: SnackbarType.success,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: AutofillGroup(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  DriftUp(
                    child: Text('Aelu', style: theme.textTheme.displayLarge),
                  ),
                  const SizedBox(height: 8),
                  DriftUp(
                    delay: const Duration(milliseconds: 100),
                    child: Text(
                      'Deep practice, not busy work.',
                      style: theme.textTheme.bodyMedium?.copyWith(color: AeluColors.mutedOf(context)),
                    ),
                  ),
                  const SizedBox(height: 48),
                  TextField(
                    controller: _emailController,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    autocorrect: false,
                    autofillHints: const [AutofillHints.email],
                    // SECURITY: Limit input length.
                    maxLength: SecurityConfig.maxEmailLength,
                    maxLengthEnforcement: MaxLengthEnforcement.enforced,
                    buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
                    onSubmitted: (_) => _passwordFocusNode.requestFocus(),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _passwordController,
                    focusNode: _passwordFocusNode,
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _obscurePassword ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                          size: 20,
                        ),
                        onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                      ),
                    ),
                    obscureText: _obscurePassword,
                    textInputAction: TextInputAction.done,
                    autofillHints: const [AutofillHints.password],
                    // SECURITY: Limit password length to prevent DoS.
                    maxLength: SecurityConfig.maxPasswordLength,
                    maxLengthEnforcement: MaxLengthEnforcement.enforced,
                    buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
                    onSubmitted: (_) => _submit(),
                  ),
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(
                      onPressed: _showForgotPasswordSheet,
                      child: Text('Forgot password?', style: theme.textTheme.bodySmall),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                  ],
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: Semantics(
                      button: true,
                      label: 'Sign in',
                      child: ElevatedButton(
                        onPressed: (_loading || _rateLimiter.isLockedOut) ? null : _submit,
                        child: _loading
                            ? const SizedBox(
                                height: 20,
                                width: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Text('Sign in'),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextButton(
                    onPressed: () => context.go('/auth/register'),
                    child: const Text('Create an account'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
