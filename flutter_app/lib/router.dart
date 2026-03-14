import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'auth/auth_provider.dart';
import 'auth/login_screen.dart';
import 'auth/register_screen.dart';
import 'auth/mfa_screen.dart';
import 'core/animations/timing.dart';
import 'theme/aelu_colors.dart';
import 'dashboard/dashboard_screen.dart';
import 'session/session_screen.dart';
import 'complete/complete_screen.dart';
import 'exposure/reader_screen.dart';
import 'exposure/media_screen.dart';
import 'exposure/listening_screen.dart';
import 'onboarding/onboarding_screen.dart';
import 'settings/settings_screen.dart';
import 'settings/profile_screen.dart';
import 'settings/mfa_settings_screen.dart';
import 'settings/notifications_screen.dart';
import 'settings/appearance_screen.dart';
import 'settings/session_prefs_screen.dart';
import 'settings/gdpr_screen.dart';
import 'settings/about_screen.dart';
import 'payments/payment_screen.dart';
import 'referrals/referral_screen.dart';
import 'grammar/grammar_screen.dart';
import 'grammar/grammar_detail_screen.dart';
import 'analytics/analytics_screen.dart';
import 'settings/voice_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    initialLocation: '/',
    redirect: (context, state) {
      // Hold on splash while restoring session.
      if (authState.isRestoring) return '/splash';

      final isAuthenticated = authState.isAuthenticated;
      final isAuthRoute = state.matchedLocation.startsWith('/auth');
      final isSplash = state.matchedLocation == '/splash';
      final isOnboarding = state.matchedLocation == '/onboarding';
      final isMfaRoute = state.matchedLocation == '/auth/mfa';

      // SECURITY: Unauthenticated users can only access auth routes.
      if (!isAuthenticated && !isAuthRoute) {
        return '/auth/login';
      }

      // SECURITY: MFA enforcement (OWASP M4, ISO 27001 A.9.4.2).
      // If MFA is required, only allow the MFA screen.
      if (authState.needsMfa && !isMfaRoute) {
        // Allow navigating away from MFA only to login (cancel).
        if (state.matchedLocation == '/auth/login') return null;
        return '/auth/mfa';
      }

      // SECURITY: Prevent accessing MFA screen without MFA challenge.
      if (isMfaRoute && !authState.needsMfa) {
        return '/auth/login';
      }

      // Authenticated users shouldn't be on auth/splash routes.
      if (isAuthenticated && !authState.needsMfa && (isAuthRoute || isSplash)) {
        return '/';
      }

      // Onboarding redirect.
      if (isAuthenticated && !authState.needsMfa &&
          authState.needsOnboarding && !isOnboarding) {
        return '/onboarding';
      }

      return null;
    },
    routes: [
      GoRoute(
        path: '/splash',
        pageBuilder: (context, state) => _crossfadePage(
          state,
          const _SplashScreen(),
        ),
      ),
      GoRoute(
        path: '/',
        pageBuilder: (context, state) => _slidePage(state, const DashboardScreen()),
      ),
      GoRoute(
        path: '/auth/login',
        pageBuilder: (context, state) => _crossfadePage(state, const LoginScreen()),
      ),
      GoRoute(
        path: '/auth/register',
        pageBuilder: (context, state) => _crossfadePage(state, const RegisterScreen()),
      ),
      GoRoute(
        path: '/auth/mfa',
        pageBuilder: (context, state) => _crossfadePage(state, const MfaScreen()),
      ),
      GoRoute(
        path: '/onboarding',
        pageBuilder: (context, state) => _crossfadePage(state, const OnboardingScreen()),
      ),
      GoRoute(
        path: '/session/:type',
        pageBuilder: (context, state) {
          // SECURITY: Validate session type parameter.
          final type = state.pathParameters['type'] ?? 'full';
          final validTypes = {'full', 'mini'};
          final safeType = validTypes.contains(type) ? type : 'full';
          return _slideUpPage(state, SessionScreen(sessionType: safeType));
        },
      ),
      GoRoute(
        path: '/complete',
        pageBuilder: (context, state) {
          final results = state.extra as Map<String, dynamic>?;
          return _slideUpPage(state, CompleteScreen(results: results ?? {}));
        },
      ),
      GoRoute(
        path: '/reading',
        pageBuilder: (context, state) => _slidePage(state, const ReaderScreen()),
      ),
      GoRoute(
        path: '/media',
        pageBuilder: (context, state) => _slidePage(state, const MediaScreen()),
      ),
      GoRoute(
        path: '/listening',
        pageBuilder: (context, state) => _slidePage(state, const ListeningScreen()),
      ),
      GoRoute(
        path: '/settings',
        pageBuilder: (context, state) => _slidePage(state, const SettingsScreen()),
      ),
      GoRoute(
        path: '/settings/profile',
        pageBuilder: (context, state) => _slidePage(state, const ProfileScreen()),
      ),
      GoRoute(
        path: '/settings/mfa',
        pageBuilder: (context, state) => _slidePage(state, const MfaSettingsScreen()),
      ),
      GoRoute(
        path: '/settings/notifications',
        pageBuilder: (context, state) => _slidePage(state, const NotificationsScreen()),
      ),
      GoRoute(
        path: '/settings/appearance',
        pageBuilder: (context, state) => _slidePage(state, const AppearanceScreen()),
      ),
      GoRoute(
        path: '/settings/session-prefs',
        pageBuilder: (context, state) => _slidePage(state, const SessionPrefsScreen()),
      ),
      GoRoute(
        path: '/settings/gdpr',
        pageBuilder: (context, state) => _slidePage(state, const GdprScreen()),
      ),
      GoRoute(
        path: '/settings/about',
        pageBuilder: (context, state) => _slidePage(state, const AboutScreen()),
      ),
      GoRoute(
        path: '/payments',
        pageBuilder: (context, state) => _slideUpPage(state, const PaymentScreen()),
      ),
      GoRoute(
        path: '/referrals',
        pageBuilder: (context, state) => _slidePage(state, const ReferralScreen()),
      ),
      GoRoute(
        path: '/grammar',
        pageBuilder: (context, state) => _slidePage(state, const GrammarScreen()),
      ),
      GoRoute(
        path: '/grammar/:id',
        pageBuilder: (context, state) {
          final id = int.tryParse(state.pathParameters['id'] ?? '') ?? 0;
          return _slidePage(state, GrammarDetailScreen(pointId: id));
        },
      ),
      GoRoute(
        path: '/analytics',
        pageBuilder: (context, state) => _slidePage(state, const AnalyticsScreen()),
      ),
      GoRoute(
        path: '/settings/voice',
        pageBuilder: (context, state) => _slidePage(state, const VoiceScreen()),
      ),
    ],
  );
});

// ── Custom page transitions ──

/// Slide from right — standard forward navigation (300ms, easeUpward).
CustomTransitionPage<void> _slidePage(GoRouterState state, Widget child) {
  return CustomTransitionPage(
    key: state.pageKey,
    child: child,
    transitionDuration: const Duration(milliseconds: 300),
    reverseTransitionDuration: const Duration(milliseconds: 300),
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      final curved = CurvedAnimation(
        parent: animation,
        curve: AeluTiming.easeUpward,
      );
      return SlideTransition(
        position: Tween<Offset>(
          begin: const Offset(1, 0),
          end: Offset.zero,
        ).animate(curved),
        child: child,
      );
    },
  );
}

/// Slide from bottom — modal screens (session, complete, payments).
CustomTransitionPage<void> _slideUpPage(GoRouterState state, Widget child) {
  return CustomTransitionPage(
    key: state.pageKey,
    child: child,
    transitionDuration: const Duration(milliseconds: 300),
    reverseTransitionDuration: const Duration(milliseconds: 300),
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      final curved = CurvedAnimation(
        parent: animation,
        curve: AeluTiming.easeUpward,
      );
      return SlideTransition(
        position: Tween<Offset>(
          begin: const Offset(0, 1),
          end: Offset.zero,
        ).animate(curved),
        child: child,
      );
    },
  );
}

/// Crossfade — auth screens (250ms).
CustomTransitionPage<void> _crossfadePage(GoRouterState state, Widget child) {
  return CustomTransitionPage(
    key: state.pageKey,
    child: child,
    transitionDuration: const Duration(milliseconds: 250),
    reverseTransitionDuration: const Duration(milliseconds: 250),
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      return FadeTransition(opacity: animation, child: child);
    },
  );
}

/// Minimal splash shown while restoring session.
class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Aelu',
              style: TextStyle(
                fontFamily: 'CormorantGaramond',
                fontSize: 36,
                fontWeight: FontWeight.w600,
                color: theme.textTheme.displayLarge?.color,
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: AeluColors.mutedOf(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
