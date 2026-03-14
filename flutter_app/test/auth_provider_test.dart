import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/auth/auth_provider.dart';

void main() {
  group('AuthState defaults', () {
    test('defaults to isRestoring true', () {
      const state = AuthState();
      expect(state.isRestoring, true);
      expect(state.isAuthenticated, false);
      expect(state.needsOnboarding, false);
      expect(state.needsMfa, false);
      expect(state.mfaChallengeId, isNull);
      expect(state.accessToken, isNull);
    });
  });

  group('AuthState.copyWith', () {
    test('preserves unmodified fields', () {
      const state = AuthState(
        accessToken: 'tok',
        isAuthenticated: true,
        isRestoring: false,
      );
      final updated = state.copyWith(needsOnboarding: true);
      expect(updated.accessToken, 'tok');
      expect(updated.isAuthenticated, true);
      expect(updated.needsOnboarding, true);
      expect(updated.isRestoring, false);
    });

    test('updates multiple fields', () {
      const state = AuthState();
      final updated = state.copyWith(
        accessToken: 'new-tok',
        isAuthenticated: true,
        isRestoring: false,
        needsMfa: true,
        mfaChallengeId: 'ch-123',
      );
      expect(updated.accessToken, 'new-tok');
      expect(updated.isAuthenticated, true);
      expect(updated.isRestoring, false);
      expect(updated.needsMfa, true);
      expect(updated.mfaChallengeId, 'ch-123');
    });

    test('completeOnboarding sets needsOnboarding to false', () {
      const state = AuthState(
        isAuthenticated: true,
        needsOnboarding: true,
        isRestoring: false,
      );
      final updated = state.copyWith(needsOnboarding: false);
      expect(updated.needsOnboarding, false);
      expect(updated.isAuthenticated, true);
    });

    test('can transition from restoring to authenticated', () {
      const state = AuthState(isRestoring: true);
      final updated = state.copyWith(
        isRestoring: false,
        isAuthenticated: true,
        accessToken: 'jwt',
      );
      expect(updated.isRestoring, false);
      expect(updated.isAuthenticated, true);
      expect(updated.accessToken, 'jwt');
    });

    test('can transition from restoring to unauthenticated', () {
      const state = AuthState(isRestoring: true);
      final updated = state.copyWith(isRestoring: false);
      expect(updated.isRestoring, false);
      expect(updated.isAuthenticated, false);
    });

    test('MFA flow state transitions', () {
      // Login returns MFA required.
      const initial = AuthState(isRestoring: false);
      final mfaRequired = initial.copyWith(
        needsMfa: true,
        mfaChallengeId: 'challenge-abc',
      );
      expect(mfaRequired.needsMfa, true);
      expect(mfaRequired.mfaChallengeId, 'challenge-abc');
      expect(mfaRequired.isAuthenticated, false);

      // MFA verified → authenticated.
      final authenticated = mfaRequired.copyWith(
        needsMfa: false,
        isAuthenticated: true,
        accessToken: 'access-tok',
      );
      expect(authenticated.needsMfa, false);
      expect(authenticated.isAuthenticated, true);
      expect(authenticated.accessToken, 'access-tok');
    });
  });

  group('AuthState — logout scenario', () {
    test('logout resets to clean state', () {
      // Simulate logout: create fresh AuthState with isRestoring false.
      const loggedOut = AuthState(isRestoring: false);
      expect(loggedOut.isAuthenticated, false);
      expect(loggedOut.accessToken, isNull);
      expect(loggedOut.needsOnboarding, false);
      expect(loggedOut.needsMfa, false);
      expect(loggedOut.mfaChallengeId, isNull);
      expect(loggedOut.isRestoring, false);
    });
  });
}
