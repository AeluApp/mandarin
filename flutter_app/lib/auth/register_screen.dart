import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_client.dart';
import '../core/animations/drift_up.dart';
import '../core/error_handler.dart';
import '../core/security/security_config.dart';
import '../shared/widgets/aelu_snackbar.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _loading = false;
  bool _obscurePassword = true;
  bool _acceptedTerms = false;
  String? _error;

  // SECURITY: Rate limiting on registration (OWASP M4).
  final _rateLimiter = RateLimiter(
    maxAttempts: SecurityConfig.maxLoginAttempts,
  );

  @override
  void initState() {
    super.initState();
    ScreenshotGuard.enable();
  }

  @override
  void dispose() {
    // SECURITY: Clear sensitive data.
    _emailController.clear();
    _passwordController.clear();
    _confirmController.clear();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    ScreenshotGuard.disable();
    super.dispose();
  }

  Future<void> _submit() async {
    unawaited(HapticFeedback.selectionClick());
    if (_rateLimiter.isLockedOut) {
      final remaining = _rateLimiter.remainingLockout;
      setState(() => _error =
          'Too many attempts. Try again in ${remaining?.inSeconds ?? 30}s.');
      return;
    }

    // SECURITY: Sanitize and validate email.
    final email = InputSanitizer.sanitize(
        _emailController.text, maxLength: SecurityConfig.maxEmailLength);
    final password = _passwordController.text;

    if (!InputSanitizer.isValidEmail(email)) {
      setState(() => _error = 'That doesn\'t look like an email address.');
      return;
    }

    // SECURITY: Stronger password validation (NIST SP 800-63B).
    final strengthIssue = InputSanitizer.passwordStrengthIssue(password);
    if (strengthIssue != null) {
      setState(() => _error = strengthIssue);
      return;
    }

    if (password != _confirmController.text) {
      setState(() => _error = 'Those passwords don\'t match.');
      return;
    }

    if (!_acceptedTerms) {
      setState(() => _error = 'You\'ll need to accept the terms to continue.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      await ref.read(apiClientProvider).post('/api/auth/register', data: {
        'email': email,
        'password': password,
      });

      _rateLimiter.recordSuccess();

      if (!mounted) return;
      AeluSnackbar.show(
        context,
        'Welcome to Aelu! Sign in to get started.',
        type: SnackbarType.success,
      );
      context.go('/auth/login');
    } catch (e, st) {
      ErrorHandler.log('Register submit', e, st);
      _rateLimiter.recordFailure();
      // SECURITY: Generic error message.
      setState(() => _error = 'Something went wrong. Check your connection and try again.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Create Account')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
          child: AutofillGroup(
            child: Column(
              children: [
                DriftUp(
                  child: TextField(
                    controller: _emailController,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    autocorrect: false,
                    autofillHints: const [AutofillHints.email],
                    maxLength: SecurityConfig.maxEmailLength,
                    maxLengthEnforcement: MaxLengthEnforcement.enforced,
                    buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
                  ),
                ),
                const SizedBox(height: 16),
                DriftUp(
                  delay: const Duration(milliseconds: 50),
                  child: TextField(
                    controller: _passwordController,
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
                      helperText: 'At least 8 characters with uppercase, lowercase, number, and symbol',
                      helperMaxLines: 2,
                    ),
                    obscureText: _obscurePassword,
                    textInputAction: TextInputAction.next,
                    autofillHints: const [AutofillHints.newPassword],
                    maxLength: SecurityConfig.maxPasswordLength,
                    maxLengthEnforcement: MaxLengthEnforcement.enforced,
                    buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
                  ),
                ),
                const SizedBox(height: 16),
                DriftUp(
                  delay: const Duration(milliseconds: 100),
                  child: TextField(
                    controller: _confirmController,
                    decoration: const InputDecoration(
                      labelText: 'Confirm password',
                      prefixIcon: Icon(Icons.lock_outline),
                    ),
                    obscureText: true,
                    textInputAction: TextInputAction.done,
                    maxLength: SecurityConfig.maxPasswordLength,
                    maxLengthEnforcement: MaxLengthEnforcement.enforced,
                    buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
                    onSubmitted: (_) => _submit(),
                  ),
                ),
                const SizedBox(height: 16),
                DriftUp(
                  delay: const Duration(milliseconds: 150),
                  child: CheckboxListTile(
                    value: _acceptedTerms,
                    onChanged: (v) => setState(() => _acceptedTerms = v ?? false),
                    title: Text(
                      'I accept the Terms of Service and Privacy Policy',
                      style: theme.textTheme.bodySmall,
                    ),
                    controlAffinity: ListTileControlAffinity.leading,
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 8),
                  Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                ],
                const SizedBox(height: 16),
                DriftUp(
                  delay: const Duration(milliseconds: 200),
                  child: SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: (_loading || _rateLimiter.isLockedOut) ? null : _submit,
                      child: _loading
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Create account'),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                DriftUp(
                  delay: const Duration(milliseconds: 250),
                  child: TextButton(
                    onPressed: () => context.go('/auth/login'),
                    child: const Text('Already have an account? Sign in'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
