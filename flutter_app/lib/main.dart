import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/app_lifecycle.dart';
import 'core/error_handler.dart';
import 'core/notification_scheduler.dart';
import 'core/sound/aelu_sound.dart';
import 'core/theme_controller.dart';
import 'router.dart';
import 'theme/aelu_theme.dart';

const _apiUrl =
    String.fromEnvironment('API_URL', defaultValue: 'http://localhost:5173');

void main() {
  runZonedGuarded(() {
    WidgetsFlutterBinding.ensureInitialized();

    // Initialize error handler with API URL.
    ErrorHandler.init(_apiUrl);

    FlutterError.onError = ErrorHandler.onFlutterError;

    // SECURITY: In release mode, suppress framework error details from console
    // to prevent information leakage (OWASP M9, NIST SI-11).
    if (kReleaseMode) {
      FlutterError.onError = (details) {
        // Log to our handler (which scrubs PII) but don't print to console.
        ErrorHandler.onFlutterError(details);
      };
    }

    runApp(const ProviderScope(child: AeluApp()));
  }, ErrorHandler.onPlatformError);
}

class AeluApp extends ConsumerStatefulWidget {
  const AeluApp({super.key});

  @override
  ConsumerState<AeluApp> createState() => _AeluAppState();
}

class _AeluAppState extends ConsumerState<AeluApp> {
  late final AppLifecycleObserver _lifecycleObserver;

  @override
  void initState() {
    super.initState();
    ref.read(soundProvider).init();
    ref.read(notificationSchedulerProvider).init();
    _lifecycleObserver = AppLifecycleObserver(ref);
    WidgetsBinding.instance.addObserver(_lifecycleObserver);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(_lifecycleObserver);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    final themeMode = ref.watch(themeControllerProvider);

    return MaterialApp.router(
      title: 'Aelu',
      debugShowCheckedModeBanner: false,
      restorationScopeId: 'aelu_app',
      theme: AeluTheme.light(),
      darkTheme: AeluTheme.dark(),
      themeMode: themeMode,
      routerConfig: router,
    );
  }
}
