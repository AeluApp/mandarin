import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/offline_queue.dart';
import '../auth/auth_provider.dart';
import 'security/security_config.dart';

/// App lifecycle observer — checkpoint on pause, restore on resume,
/// session timeout on background.
///
/// Security controls:
/// - OWASP M1 (Improper Platform Usage): Proper lifecycle handling.
/// - ISO 27001 A.11.2.8 (Unattended user equipment): Auto-timeout.
/// - NIST AC-12 (Session Termination): Background timeout auto-logout.
/// - CIS Mobile 4.5 (Session Management): Idle and background timeouts.
class AppLifecycleObserver extends WidgetsBindingObserver {
  final WidgetRef _ref;
  DateTime? _backgroundedAt;
  DateTime? _lastInteraction;

  AppLifecycleObserver(this._ref) {
    _lastInteraction = DateTime.now();
  }

  /// Call this on any user interaction to reset idle timer.
  void recordInteraction() {
    _lastInteraction = DateTime.now();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.inactive:
        // Record when app went to background.
        _backgroundedAt = DateTime.now();
        // Flush offline queue on pause.
        _ref.read(offlineQueueProvider).flush();
        break;

      case AppLifecycleState.resumed:
        _checkSessionTimeout();
        // Flush queue on resume.
        _ref.read(offlineQueueProvider).flush();
        _lastInteraction = DateTime.now();
        break;

      default:
        break;
    }
  }

  /// Check if session has expired due to background time or idle time.
  void _checkSessionTimeout() {
    final authState = _ref.read(authProvider);
    if (!authState.isAuthenticated) return;

    // Check background timeout.
    if (_backgroundedAt != null) {
      final elapsed = DateTime.now().difference(_backgroundedAt!);
      if (elapsed > SecurityConfig.backgroundTimeout) {
        _forceLogout();
        return;
      }
    }

    // Check idle timeout.
    if (_lastInteraction != null) {
      final idle = DateTime.now().difference(_lastInteraction!);
      if (idle > SecurityConfig.sessionTimeout) {
        _forceLogout();
        return;
      }
    }
  }

  void _forceLogout() {
    _ref.read(authProvider.notifier).logoutExpired();
  }
}
