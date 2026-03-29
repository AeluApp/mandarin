/// Hardware-backed secure token storage.
///
/// Uses flutter_secure_storage (KeyChain on iOS, Keystore on Android)
/// for JWT tokens and sensitive credentials.
///
/// This is a higher-level API built on top of [SecureStore] from
/// security_config.dart, specializing in token lifecycle management
/// with graceful fallback when secure storage is unavailable.
///
/// Security references:
/// - OWASP M2 (Insecure Data Storage): Hardware-backed encryption.
/// - NIST SC-28 (Protection of Information at Rest): Encrypted at rest.
/// - ISO 27001 A.10.1.1 (Cryptographic controls): Platform keystore.
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureTokenStorage {
  SecureTokenStorage._();

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.first_unlock,
    ),
  );

  // ── Token keys ──

  static const _accessTokenKey = 'aelu_access_token';
  static const _refreshTokenKey = 'aelu_refresh_token';

  // ── Access token ──

  /// Persist the access token to secure storage.
  ///
  /// Returns silently on failure — callers should not depend on
  /// storage success for request flow (the in-memory token in
  /// [ApiClient] is the primary source during a session).
  static Future<void> saveAccessToken(String token) async {
    await save(_accessTokenKey, token);
  }

  /// Retrieve the persisted access token, or null if absent or
  /// storage is unavailable.
  static Future<String?> getAccessToken() async {
    return get(_accessTokenKey);
  }

  // ── Refresh token ──

  /// Persist the refresh token to secure storage.
  static Future<void> saveRefreshToken(String token) async {
    await save(_refreshTokenKey, token);
  }

  /// Retrieve the persisted refresh token, or null if absent or
  /// storage is unavailable.
  static Future<String?> getRefreshToken() async {
    return get(_refreshTokenKey);
  }

  // ── Bulk operations ──

  /// Delete both access and refresh tokens.
  ///
  /// Call on logout to ensure no stale credentials remain on device.
  static Future<void> deleteAll() async {
    try {
      await _storage.deleteAll();
    } catch (e, st) {
      _logError('deleteAll', e, st);
    }
  }

  // ── Generic key-value API ──

  /// Save an arbitrary key-value pair to secure storage.
  ///
  /// Use this for non-token secrets (e.g. encryption keys, API keys)
  /// that need hardware-backed protection.
  static Future<void> save(String key, String value) async {
    try {
      await _storage.write(key: key, value: value);
    } catch (e, st) {
      _logError('save($key)', e, st);
    }
  }

  /// Retrieve a value by key, or null if absent or on failure.
  static Future<String?> get(String key) async {
    try {
      return await _storage.read(key: key);
    } catch (e, st) {
      _logError('get($key)', e, st);
      return null;
    }
  }

  /// Delete a single key from secure storage.
  static Future<void> delete(String key) async {
    try {
      await _storage.delete(key: key);
    } catch (e, st) {
      _logError('delete($key)', e, st);
    }
  }

  // ── Internal ──

  /// Log storage errors in debug mode only — no PII in release logs.
  static void _logError(String operation, Object error, StackTrace st) {
    if (kDebugMode) {
      debugPrint('SecureTokenStorage.$operation failed: $error');
    }
    // In production, this would route to a privacy-safe error reporter.
    // PII scrubbing is handled by PiiScrubber in security_config.dart.
  }
}
