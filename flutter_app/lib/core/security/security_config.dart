import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Central security configuration for Aelu.
///
/// Covers OWASP Mobile Top 10, NIST SP 800-163, ISO 27001 Annex A,
/// CIS Mobile Benchmarks.
class SecurityConfig {
  SecurityConfig._();

  // ── Certificate pinning (OWASP M3, NIST IA-5) ──

  /// SHA-256 public key hashes of the server certificate chain.
  /// Update these when rotating server certificates.
  static const List<String> pinnedCertHashes = [
    // Primary cert hash — replace with actual production cert hash.
    // Generate with: openssl s_client -connect aeluapp.com:443 | \
    //   openssl x509 -pubkey -noout | openssl pkey -pubin -outform DER | \
    //   openssl dgst -sha256 -binary | openssl enc -base64
    'CONFIGURE_BEFORE_RELEASE',
    // Backup cert hash (for rotation).
    'CONFIGURE_BEFORE_RELEASE_BACKUP',
  ];

  /// Whether to enforce cert pinning. Disabled in debug builds.
  static bool get enforcePinning => !kDebugMode;

  // ── Session timeout (ISO 27001 A.11.2.8, NIST AC-12) ──

  /// Maximum idle time before auto-logout.
  static const Duration sessionTimeout = Duration(minutes: 30);

  /// Maximum background time before requiring re-authentication.
  static const Duration backgroundTimeout = Duration(minutes: 15);

  // ── Rate limiting (OWASP M4, CIS 3.2) ──

  /// Max login attempts before lockout.
  static const int maxLoginAttempts = 5;

  /// Max MFA attempts before lockout.
  static const int maxMfaAttempts = 3;

  /// Base lockout duration (doubles each cycle).
  static const Duration baseLockoutDuration = Duration(seconds: 30);

  /// Maximum lockout duration.
  static const Duration maxLockoutDuration = Duration(minutes: 15);

  // ── Input validation ──

  /// Maximum length for text input fields.
  static const int maxInputLength = 500;

  /// Maximum length for email fields.
  static const int maxEmailLength = 254;

  /// Maximum length for password fields.
  static const int maxPasswordLength = 128;

  /// Minimum password length.
  static const int minPasswordLength = 8;

  // ── Allowed deep link paths (OWASP M1) ──

  static const Set<String> allowedDeepLinkPaths = {
    '/',
    '/dashboard',
    '/session/full',
    '/session/mini',
    '/reading',
    '/media',
    '/listening',
    '/settings',
    '/payments',
    '/referrals',
    '/auth/login',
    '/auth/register',
    '/referral',
  };
}

/// Client-side rate limiter with exponential backoff.
///
/// OWASP M4 (Insufficient Input/Output Validation),
/// CIS Mobile Benchmark 3.2 (Authentication Throttling).
class RateLimiter {
  int _attempts = 0;
  DateTime? _lockoutUntil;
  final int _maxAttempts;
  final Duration _baseLockout;
  final Duration _maxLockout;
  int _lockoutCycles = 0;

  RateLimiter({
    int maxAttempts = SecurityConfig.maxLoginAttempts,
    Duration baseLockout = SecurityConfig.baseLockoutDuration,
    Duration maxLockout = SecurityConfig.maxLockoutDuration,
  })  : _maxAttempts = maxAttempts,
        _baseLockout = baseLockout,
        _maxLockout = maxLockout;

  /// Check if currently locked out.
  bool get isLockedOut {
    if (_lockoutUntil == null) return false;
    if (DateTime.now().isAfter(_lockoutUntil!)) {
      // Lockout expired — reset attempts but keep cycle count.
      _lockoutUntil = null;
      _attempts = 0;
      return false;
    }
    return true;
  }

  /// Remaining lockout duration, or null if not locked out.
  Duration? get remainingLockout {
    if (!isLockedOut) return null;
    return _lockoutUntil!.difference(DateTime.now());
  }

  /// Record a failed attempt. Returns true if now locked out.
  bool recordFailure() {
    _attempts++;
    if (_attempts >= _maxAttempts) {
      _lockoutCycles++;
      final lockoutSeconds =
          (_baseLockout.inSeconds * (1 << (_lockoutCycles - 1)))
              .clamp(0, _maxLockout.inSeconds);
      _lockoutUntil = DateTime.now().add(Duration(seconds: lockoutSeconds));
      return true;
    }
    return false;
  }

  /// Record a successful attempt — reset everything.
  void recordSuccess() {
    _attempts = 0;
    _lockoutCycles = 0;
    _lockoutUntil = null;
  }

  /// Number of remaining attempts before lockout.
  int get remainingAttempts => (_maxAttempts - _attempts).clamp(0, _maxAttempts);
}

/// Input sanitizer — validates and cleans user input.
///
/// OWASP M4 (Insufficient Input/Output Validation).
class InputSanitizer {
  InputSanitizer._();

  /// Sanitize a text input — trim, limit length, strip control chars.
  static String sanitize(String input, {int maxLength = SecurityConfig.maxInputLength}) {
    // Trim whitespace.
    var cleaned = input.trim();
    // Remove control characters (except newline, tab).
    cleaned = cleaned.replaceAll(RegExp(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]'), '');
    // Enforce length limit.
    if (cleaned.length > maxLength) {
      cleaned = cleaned.substring(0, maxLength);
    }
    return cleaned;
  }

  /// Validate email format.
  static bool isValidEmail(String email) {
    if (email.length > SecurityConfig.maxEmailLength) return false;
    // RFC 5322 simplified — reject obviously invalid patterns.
    return RegExp(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
        .hasMatch(email);
  }

  /// Validate password strength.
  static String? passwordStrengthIssue(String password) {
    if (password.length < SecurityConfig.minPasswordLength) {
      return 'At least ${SecurityConfig.minPasswordLength} characters';
    }
    if (password.length > SecurityConfig.maxPasswordLength) {
      return 'Password too long';
    }
    if (!password.contains(RegExp(r'[A-Z]'))) return 'Add an uppercase letter';
    if (!password.contains(RegExp(r'[a-z]'))) return 'Add a lowercase letter';
    if (!password.contains(RegExp(r'[0-9]'))) return 'Add a number';
    if (!password.contains(RegExp(r'[!@#$%^&*(),.?":{}|<>]'))) {
      return 'Add a special character';
    }
    return null;
  }

  /// Sanitize a deep link path — only allow whitelisted paths.
  static String? sanitizeDeepLinkPath(String path) {
    // Normalize: remove trailing slash, decode.
    var normalized = Uri.decodeFull(path).replaceAll(RegExp(r'/+$'), '');
    if (normalized.isEmpty) normalized = '/';

    // Block path traversal.
    if (normalized.contains('..') || normalized.contains('\x00')) {
      return null;
    }

    // Check whitelist.
    if (SecurityConfig.allowedDeepLinkPaths.contains(normalized)) {
      return normalized;
    }

    return null;
  }

  /// Sanitize deep link query parameters — remove known dangerous keys.
  static Map<String, String> sanitizeQueryParams(Map<String, String> params) {
    const blockedKeys = {'token', 'access_token', 'refresh_token', 'password',
        'secret', 'key', 'api_key'};
    final cleaned = <String, String>{};
    for (final entry in params.entries) {
      final key = entry.key.toLowerCase();
      if (blockedKeys.contains(key)) continue;
      // Limit value length.
      var value = entry.value;
      if (value.length > 200) value = value.substring(0, 200);
      cleaned[entry.key] = value;
    }
    return cleaned;
  }
}

/// PII scrubber for analytics and error reporting.
///
/// ISO 27001 A.18.1.4 (Privacy and protection of PII),
/// NIST SI-11 (Error Handling).
class PiiScrubber {
  PiiScrubber._();

  static final _emailPattern = RegExp(
      r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}');
  static final _tokenPattern = RegExp(
      r'(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})');
  static final _passwordPattern = RegExp(
      r'(password|passwd|pwd|secret|token|key|authorization)["\s:=]+["\s]*[^\s"]{1,}',
      caseSensitive: false);

  /// Scrub PII from a string — replaces emails, tokens, passwords.
  static String scrub(String input) {
    var scrubbed = input;
    scrubbed = scrubbed.replaceAll(_emailPattern, '[EMAIL]');
    scrubbed = scrubbed.replaceAll(_tokenPattern, '[TOKEN]');
    scrubbed = scrubbed.replaceAll(_passwordPattern, '[REDACTED]');
    return scrubbed;
  }

  /// Scrub PII from a map (recursively).
  static Map<String, dynamic> scrubMap(Map<String, dynamic> data) {
    const sensitiveKeys = {
      'email', 'password', 'token', 'access_token', 'refresh_token',
      'secret', 'key', 'api_key', 'authorization', 'cookie',
      'phone', 'address', 'ssn', 'credit_card',
    };

    final result = <String, dynamic>{};
    for (final entry in data.entries) {
      final keyLower = entry.key.toLowerCase();
      if (sensitiveKeys.contains(keyLower)) {
        result[entry.key] = '[REDACTED]';
      } else if (entry.value is String) {
        result[entry.key] = scrub(entry.value as String);
      } else if (entry.value is Map<String, dynamic>) {
        result[entry.key] = scrubMap(entry.value as Map<String, dynamic>);
      } else {
        result[entry.key] = entry.value;
      }
    }
    return result;
  }

  /// Truncate a stack trace to N frames and strip local paths.
  static String? sanitizeStackTrace(String? stack, {int maxFrames = 5}) {
    if (stack == null) return null;
    final lines = stack.split('\n');
    final truncated = lines.take(maxFrames).toList();
    // Strip absolute local paths (keep relative from lib/).
    return truncated.map((line) {
      return line.replaceAll(
          RegExp(r'/[^\s]*?/(lib/)'), 'lib/');
    }).join('\n');
  }
}

/// Screenshot prevention for sensitive screens.
///
/// OWASP M9 (Reverse Engineering), CIS Mobile 4.3.
class ScreenshotGuard {
  ScreenshotGuard._();

  /// Prevent screenshots on the current screen (Android: FLAG_SECURE, iOS: blur on task switcher).
  static Future<void> enable() async {
    if (Platform.isAndroid) {
      // Android: FLAG_SECURE prevents screenshots and screen recording.
      await const MethodChannel('aelu/security')
          .invokeMethod('enableSecureFlag');
    }
    // iOS: Handled by hiding content in AppDelegate applicationWillResignActive.
  }

  /// Re-allow screenshots.
  static Future<void> disable() async {
    if (Platform.isAndroid) {
      await const MethodChannel('aelu/security')
          .invokeMethod('disableSecureFlag');
    }
  }
}

/// Encrypted storage wrapper — all sensitive data goes through this.
///
/// OWASP M2 (Insecure Data Storage), NIST SC-28 (Protection of Information at Rest).
class SecureStore {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.first_unlock_this_device,
    ),
  );

  /// Read a value from secure storage.
  static Future<String?> read(String key) => _storage.read(key: key);

  /// Write a value to secure storage.
  static Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  /// Delete a value from secure storage.
  static Future<void> delete(String key) => _storage.delete(key: key);

  /// Delete all values from secure storage.
  static Future<void> deleteAll() => _storage.deleteAll();

  /// Check if a key exists.
  static Future<bool> containsKey(String key) =>
      _storage.containsKey(key: key);
}
