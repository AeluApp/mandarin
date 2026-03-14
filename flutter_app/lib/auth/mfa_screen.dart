import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/animations/drift_up.dart';
import '../core/error_handler.dart';
import '../core/security/security_config.dart';
import 'auth_provider.dart';

class MfaScreen extends ConsumerStatefulWidget {
  const MfaScreen({super.key});

  @override
  ConsumerState<MfaScreen> createState() => _MfaScreenState();
}

class _MfaScreenState extends ConsumerState<MfaScreen> {
  final List<TextEditingController> _controllers =
      List.generate(6, (_) => TextEditingController());
  final List<FocusNode> _focusNodes = List.generate(6, (_) => FocusNode());
  bool _loading = false;
  String? _error;

  // SECURITY: Rate limiting on MFA (OWASP M4, CIS 3.2).
  // Stricter than login — 3 attempts, then lockout.
  final _rateLimiter = RateLimiter(
    maxAttempts: SecurityConfig.maxMfaAttempts,
    baseLockout: const Duration(minutes: 1),
    maxLockout: const Duration(minutes: 30),
  );

  @override
  void initState() {
    super.initState();
    // SECURITY: Prevent screenshots on MFA screen.
    ScreenshotGuard.enable();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNodes[0].requestFocus();
    });
  }

  @override
  void dispose() {
    // SECURITY: Clear MFA codes from memory.
    for (final c in _controllers) {
      c.clear();
      c.dispose();
    }
    for (final f in _focusNodes) {
      f.dispose();
    }
    ScreenshotGuard.disable();
    super.dispose();
  }

  String get _code => _controllers.map((c) => c.text).join();

  void _onDigitChanged(int index, String value) {
    if (value.length == 1) {
      HapticFeedback.selectionClick();
      if (index < 5) {
        _focusNodes[index + 1].requestFocus();
      }
    }
    if (_code.length == 6) {
      _submit();
    }
  }

  Future<void> _submit() async {
    final code = _code;
    if (code.length != 6) return;

    // SECURITY: Check rate limiter.
    if (_rateLimiter.isLockedOut) {
      final remaining = _rateLimiter.remainingLockout;
      setState(() => _error =
          'Too many attempts. Try again in ${_formatDuration(remaining)}.');
      return;
    }

    // SECURITY: Validate code is digits only.
    if (!RegExp(r'^\d{6}$').hasMatch(code)) {
      setState(() => _error = 'Code must be 6 digits.');
      _clearCode();
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      await ref.read(authProvider.notifier).submitMfa(code);
      _rateLimiter.recordSuccess();
    } catch (e, st) {
      ErrorHandler.log('MFA submit', e, st);
      final lockedOut = _rateLimiter.recordFailure();

      if (lockedOut) {
        final remaining = _rateLimiter.remainingLockout;
        setState(() => _error =
            'Too many attempts. Try again in ${_formatDuration(remaining)}.');
      } else {
        final remaining = _rateLimiter.remainingAttempts;
        setState(() => _error =
            'Invalid code. $remaining attempt${remaining == 1 ? '' : 's'} remaining.');
      }
      _clearCode();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _clearCode() {
    for (final c in _controllers) {
      c.clear();
    }
    _focusNodes[0].requestFocus();
  }

  String _formatDuration(Duration? d) {
    if (d == null) return '30s';
    if (d.inMinutes > 0) return '${d.inMinutes}m';
    return '${d.inSeconds}s';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // SECURITY: Verify MFA is actually required (prevent direct navigation).
    final authState = ref.watch(authProvider);
    if (!authState.needsMfa) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) context.go('/auth/login');
      });
      return const Scaffold(body: SizedBox.shrink());
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Two-Factor Authentication')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              DriftUp(
                child: Text(
                  'Enter the code from your authenticator app.',
                  style: theme.textTheme.bodyLarge,
                ),
              ),
              const SizedBox(height: 32),

              // PIN-style digit boxes
              DriftUp(
                delay: const Duration(milliseconds: 100),
                child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: List.generate(6, (i) => SizedBox(
                  width: 44,
                  height: 52,
                  child: Semantics(
                    label: 'Digit ${i + 1}',
                    child: TextField(
                      controller: _controllers[i],
                      focusNode: _focusNodes[i],
                      textAlign: TextAlign.center,
                      keyboardType: TextInputType.number,
                      maxLength: 1,
                      style: theme.textTheme.headlineMedium,
                      decoration: const InputDecoration(
                        counterText: '',
                        contentPadding: EdgeInsets.symmetric(vertical: 12),
                      ),
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                      onChanged: (v) => _onDigitChanged(i, v),
                      // SECURITY: Disable paste on individual digit fields.
                      enableInteractiveSelection: false,
                    ),
                  ),
                )),
              ),
              ),

              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
              ],

              const SizedBox(height: 24),
              DriftUp(
                delay: const Duration(milliseconds: 200),
                child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: (_code.length == 6 && !_rateLimiter.isLockedOut)
                            ? _submit
                            : null,
                        child: const Text('Verify'),
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
