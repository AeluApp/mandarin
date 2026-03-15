/// Centralised app configuration via compile-time `--dart-define` flags.
///
/// Usage:
///   flutter run --dart-define=API_URL=https://aeluapp.com
///   flutter run --dart-define=ENV=production
class AppConfig {
  AppConfig._();

  /// Base URL for the HTTP API and WebSocket connections.
  static const String apiUrl =
      String.fromEnvironment('API_URL', defaultValue: 'http://localhost:5173');

  /// Current environment name ("dev", "staging", "production").
  static const String env =
      String.fromEnvironment('ENV', defaultValue: 'dev');

  /// Whether the app is running in production mode.
  static const bool isProduction = env == 'production';
}
