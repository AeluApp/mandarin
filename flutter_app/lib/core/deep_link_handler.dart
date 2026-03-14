import 'security/security_config.dart';

/// Deep link handler for aelu:// and https://aeluapp.com/app/ URLs.
///
/// Security controls:
/// - OWASP M1 (Improper Platform Usage): Path whitelist, param sanitization.
/// - NIST AC-3 (Access Enforcement): Only allowed paths are routable.
/// - CIS Mobile 5.2 (URL Scheme Validation): Strict scheme and host checks.
class DeepLinkHandler {
  /// Map an incoming URI to a GoRouter path.
  ///
  /// Returns null for any unrecognized or potentially malicious URI.
  static String? mapUri(Uri uri) {
    // SECURITY: Only accept known schemes.
    if (uri.scheme != 'aelu' && uri.scheme != 'https' && uri.scheme != 'http') {
      return null;
    }

    // Handle aelu:// scheme.
    if (uri.scheme == 'aelu') {
      return _mapPath(uri.path, uri.queryParameters);
    }

    // Handle universal links: https://aeluapp.com/app/...
    // SECURITY: Strict host validation — no subdomains, no other hosts.
    if (uri.host == 'aeluapp.com' && uri.path.startsWith('/app/')) {
      final appPath = uri.path.substring(4); // Remove /app prefix.
      return _mapPath(appPath, uri.queryParameters);
    }

    return null;
  }

  static String? _mapPath(String path, Map<String, String> params) {
    // SECURITY: Sanitize the path using centralized validator.
    final safePath = InputSanitizer.sanitizeDeepLinkPath(path);
    if (safePath == null) return null;

    // SECURITY: Sanitize query parameters — strip tokens, passwords, etc.
    final safeParams = InputSanitizer.sanitizeQueryParams(params);

    // Direct route mappings.
    switch (safePath) {
      case '/':
      case '/dashboard':
        return '/';
      case '/session/full':
        return '/session/full';
      case '/session/mini':
        return '/session/mini';
      case '/reading':
        return '/reading';
      case '/media':
        return '/media';
      case '/listening':
        return '/listening';
      case '/settings':
        return '/settings';
      case '/payments':
        return '/payments';
      case '/referrals':
        return '/referrals';
      case '/auth/login':
        return '/auth/login';
      case '/auth/register':
        return '/auth/register';
    }

    // Referral code: aelu://referral?code=XXX
    if (safePath == '/referral' && safeParams.containsKey('code')) {
      // SECURITY: Validate referral code format (alphanumeric, max 20 chars).
      final code = safeParams['code']!;
      if (RegExp(r'^[a-zA-Z0-9]{1,20}$').hasMatch(code)) {
        return '/auth/register';
      }
      return null;
    }

    return null;
  }
}
