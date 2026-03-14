import 'dart:async';
import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import 'error_handler.dart';

/// Push notification service.
///
/// Initializes Firebase Messaging, requests permission (delayed),
/// and registers the device token with the backend.
class PushService {
  final ApiClient _api;
  bool _initialized = false;
  StreamSubscription? _tokenRefreshSub;
  StreamSubscription? _foregroundSub;
  StreamSubscription? _backgroundTapSub;

  PushService(this._api);

  /// Initialize Firebase and request notification permissions.
  /// Call this after the user has completed onboarding, not on first launch.
  Future<void> init() async {
    if (_initialized) return;

    try {
      await Firebase.initializeApp();
    } catch (e, st) {
      ErrorHandler.log('Push Firebase init', e, st);
      // Firebase may already be initialized.
    }

    final messaging = FirebaseMessaging.instance;
    final settings = await messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    if (settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional) {
      final token = await messaging.getToken();
      if (token != null) {
        await _registerToken(token);
      }

      // Listen for token refresh.
      _tokenRefreshSub = messaging.onTokenRefresh.listen(_registerToken);
    }

    // Handle foreground messages.
    _foregroundSub = FirebaseMessaging.onMessage.listen(_handleForegroundMessage);

    // Handle notification taps when app is in background.
    _backgroundTapSub = FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);

    _initialized = true;
  }

  Future<void> _registerToken(String token) async {
    final platform = Platform.isIOS ? 'ios' : 'android';
    try {
      await _api.post('/api/push/register', data: {
        'token': token,
        'platform': platform,
      });
    } catch (e, st) {
      ErrorHandler.log('Push register token', e, st);
      // Silent fail — will retry on next token refresh.
    }
  }

  void _handleForegroundMessage(RemoteMessage message) {
    // Foreground messages are handled by the app's notification system.
  }

  void _handleNotificationTap(RemoteMessage message) {
    // Navigate based on notification data.
    // The GoRouter will handle navigation from the root.
  }

  Future<void> dispose() async {
    await _tokenRefreshSub?.cancel();
    await _foregroundSub?.cancel();
    await _backgroundTapSub?.cancel();
  }
}

final pushServiceProvider = Provider<PushService>((ref) {
  final api = ref.watch(apiClientProvider);
  final service = PushService(api);
  ref.onDispose(() => service.dispose());
  return service;
});
