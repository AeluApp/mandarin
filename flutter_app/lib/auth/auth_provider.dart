import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/error_handler.dart';
import '../core/security/security_config.dart';

/// Authentication state — holds tokens and login status.
class AuthState {
  final String? accessToken;
  final bool isAuthenticated;
  final bool needsOnboarding;
  final bool needsMfa;
  final String? mfaChallengeId;
  final bool isRestoring;
  final bool sessionExpired;

  const AuthState({
    this.accessToken,
    this.isAuthenticated = false,
    this.needsOnboarding = false,
    this.needsMfa = false,
    this.mfaChallengeId,
    this.isRestoring = true,
    this.sessionExpired = false,
  });

  AuthState copyWith({
    String? accessToken,
    bool? isAuthenticated,
    bool? needsOnboarding,
    bool? needsMfa,
    String? mfaChallengeId,
    bool? isRestoring,
    bool? sessionExpired,
  }) {
    return AuthState(
      accessToken: accessToken ?? this.accessToken,
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      needsOnboarding: needsOnboarding ?? this.needsOnboarding,
      needsMfa: needsMfa ?? this.needsMfa,
      mfaChallengeId: mfaChallengeId ?? this.mfaChallengeId,
      isRestoring: isRestoring ?? this.isRestoring,
      sessionExpired: sessionExpired ?? this.sessionExpired,
    );
  }
}

/// Authentication state notifier.
///
/// Security controls:
/// - OWASP M2 (Insecure Data Storage): Tokens stored in SecureStore (Keychain/KeyStore).
/// - NIST IA-5 (Authenticator Management): Tokens cleared on logout.
/// - ISO 27001 A.9.4.3 (Password management system): No plaintext token storage.
class AuthNotifier extends StateNotifier<AuthState> {
  final ApiClient _api;

  AuthNotifier(this._api) : super(const AuthState());

  /// Try to restore session from stored refresh token.
  ///
  /// Applies a 10-second timeout to prevent indefinite hang on slow networks.
  Future<void> restoreSession() async {
    final refreshToken = await SecureStore.read('refresh_token');
    if (refreshToken == null) {
      state = state.copyWith(isRestoring: false);
      return;
    }

    try {
      final response = await _api
          .post('/api/auth/token/refresh', data: {
            'refresh_token': refreshToken,
          })
          .timeout(const Duration(seconds: 10));
      final data = response.data;
      if (data is! Map<String, dynamic>) {
        state = state.copyWith(isRestoring: false);
        return;
      }
      final accessToken = data.strOrNull('access_token');
      if (accessToken == null) {
        state = state.copyWith(isRestoring: false);
        return;
      }
      final newRefresh = data.strOrNull('refresh_token');

      if (newRefresh != null) {
        await SecureStore.write('refresh_token', newRefresh);
      }

      _api.setAccessToken(accessToken);
      state = AuthState(
        accessToken: accessToken,
        isAuthenticated: true,
        needsOnboarding: data.boolean('needs_onboarding'),
        isRestoring: false,
      );
    } on TimeoutException {
      // Network too slow — let user login manually.
      state = state.copyWith(isRestoring: false);
    } catch (e, st) {
      ErrorHandler.log('Auth restore session', e, st);
      // SECURITY: Clear invalid refresh token.
      await SecureStore.delete('refresh_token');
      state = state.copyWith(isRestoring: false);
    }
  }

  /// Login with email and password.
  Future<void> login(String email, String password) async {
    final response = await _api.post('/api/auth/token', data: {
      'email': email,
      'password': password,
    });
    final data = response.data;
    if (data is! Map<String, dynamic>) {
      throw Exception('Invalid login response');
    }

    if (data.boolean('mfa_required')) {
      state = state.copyWith(
        needsMfa: true,
        mfaChallengeId: data.strOrNull('challenge_id'),
        isRestoring: false,
      );
      return;
    }

    await _handleTokenResponse(data);
  }

  /// Submit MFA code.
  Future<void> submitMfa(String code) async {
    final response = await _api.post('/api/auth/token/mfa', data: {
      'challenge_id': state.mfaChallengeId,
      'code': code,
    });
    final data = response.data;
    if (data is! Map<String, dynamic>) {
      throw Exception('Invalid MFA response');
    }
    await _handleTokenResponse(data);
  }

  /// Mark onboarding as complete.
  void completeOnboarding() {
    state = state.copyWith(needsOnboarding: false);
  }

  /// Logout — clear tokens, reset state.
  ///
  /// SECURITY: Clear all sensitive data from memory and storage.
  Future<void> logout() async {
    _api.clearAccessToken();
    await SecureStore.delete('refresh_token');
    state = const AuthState(isRestoring: false);
  }

  /// Logout due to session timeout — sets expired flag for UI notification.
  Future<void> logoutExpired() async {
    _api.clearAccessToken();
    await SecureStore.delete('refresh_token');
    state = const AuthState(isRestoring: false, sessionExpired: true);
  }

  /// Clear session expired flag (call after showing notification).
  void clearSessionExpired() {
    if (state.sessionExpired) {
      state = state.copyWith(sessionExpired: false);
    }
  }

  Future<void> _handleTokenResponse(Map<String, dynamic> data) async {
    final accessToken = data.strOrNull('access_token');
    if (accessToken == null) return;
    final refreshToken = data.strOrNull('refresh_token');

    if (refreshToken != null) {
      await SecureStore.write('refresh_token', refreshToken);
    }

    _api.setAccessToken(accessToken);
    state = AuthState(
      accessToken: accessToken,
      isAuthenticated: true,
      needsOnboarding: data.boolean('needs_onboarding'),
      isRestoring: false,
    );
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final api = ref.watch(apiClientProvider);
  final notifier = AuthNotifier(api);
  unawaited(notifier.restoreSession());
  return notifier;
});
